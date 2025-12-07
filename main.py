"""
Pazarglobal WhatsApp Bridge
FastAPI webhook server to bridge WhatsApp (Twilio) with Agent Backend (OpenAI Agents SDK)
Replaces N8N workflow
"""
import ast
import io
import os
import uuid
import re
from fastapi import FastAPI, Request, HTTPException, Form
from fastapi.responses import Response
import httpx
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from PIL import Image

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Pazarglobal WhatsApp Bridge")

# Environment variables
AGENT_BACKEND_URL = os.getenv("AGENT_BACKEND_URL", "https://pazarglobal-agent-backend-production-4ec8.up.railway.app")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER", "+14155238886")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
SUPABASE_STORAGE_BUCKET = os.getenv("SUPABASE_STORAGE_BUCKET", "product-images")

# Initialize Twilio client
twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN) if TWILIO_ACCOUNT_SID else None

# ========== CONVERSATION HISTORY CACHE ==========
# In-memory storage: {phone_number: {"messages": [...], "last_activity": datetime}}
conversation_store: Dict[str, dict] = {}
CONVERSATION_TIMEOUT_MINUTES = 30  # Clear conversations after 30 minutes of inactivity
MAX_MEDIA_BYTES = 10 * 1024 * 1024  # 10 MB limit
MAX_MEDIA_PER_MESSAGE = 3  # Avoid WhatsApp bulk; keep under total size limits


def _extract_last_media_context(history: List[dict]) -> tuple[Optional[str], List[str]]:
    """Fetch the latest draft id and ALL media paths from prior system notes."""
    draft_id = None
    all_media_paths: List[str] = []

    for msg in reversed(history or []):
        text = msg.get("content") if isinstance(msg, dict) else None
        if not isinstance(text, str):
            continue
        if "[SYSTEM_MEDIA_NOTE]" not in text:
            continue

        # Get draft_id from first (most recent) SYSTEM_MEDIA_NOTE
        if "DRAFT_LISTING_ID=" in text and not draft_id:
            draft_id = text.split("DRAFT_LISTING_ID=", 1)[1].split("|")[0].strip()

        # Collect ALL media paths from all SYSTEM_MEDIA_NOTE entries
        if "MEDIA_PATHS=" in text:
            raw_paths = text.split("MEDIA_PATHS=", 1)[1].split("|")[0].strip()
            try:
                parsed = ast.literal_eval(raw_paths)
                if isinstance(parsed, list):
                    # Add paths that aren't already in the list (avoid duplicates)
                    for p in parsed:
                        if isinstance(p, str) and p not in all_media_paths:
                            all_media_paths.append(p)
            except Exception:
                pass

    return draft_id, all_media_paths


def _sanitize_user_id(user_id: str) -> str:
    # Twilio phone comes as +90..., remove plus and spaces for path safety
    return (user_id or "unknown").replace("+", "").replace(" ", "")


def _build_storage_path(user_id: str, listing_uuid: str, media_type: Optional[str]) -> str:
    ext = (media_type or "image/jpeg").split("/")[-1] or "jpg"
    return f"{_sanitize_user_id(user_id)}/{listing_uuid}/{uuid.uuid4()}.{ext}"


async def download_media(media_url: str, media_type: Optional[str], message_sid: Optional[str], media_sid: Optional[str]) -> Optional[tuple[bytes, str]]:
    if not media_url:
        return None
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        logger.warning("Twilio credentials missing, cannot fetch media")
        return None
    try:
        logger.info(f"📥 Downloading media from: {media_url[:80]}...")
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(media_url, auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN))
        
        logger.info(f"📊 Download response: status={resp.status_code}, content-type={resp.headers.get('Content-Type')}")
        
        if resp.status_code == 404 and twilio_client and message_sid and media_sid:
            logger.warning(f"⚠️ Direct URL returned 404, trying Twilio API fallback...")
            try:
                media_obj = twilio_client.messages(message_sid).media(media_sid).fetch()
                # Twilio returns uri like /2010-04-01/Accounts/AC.../Messages/MM.../Media/ME....json
                fallback_url = f"https://api.twilio.com{media_obj.uri.replace('.json','')}"
                logger.info(f"🔄 Fallback URL: {fallback_url}")
                async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                    resp = await client.get(fallback_url, auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN))
                logger.info(f"📊 Fallback response: status={resp.status_code}")
            except Exception as tw_err:
                logger.error(f"❌ Twilio fallback media fetch failed: {tw_err}")
                return None

        if not resp.is_success:
            logger.error(f"❌ Failed to download media: status={resp.status_code}, body={resp.text[:200]}")
            return None
        
        content_type = resp.headers.get("Content-Type", media_type or "")
        if not content_type.startswith("image/"):
            logger.warning(f"⚠️ Blocked non-image media: {content_type}")
            return None
        
        content = resp.content
        if content and len(content) > MAX_MEDIA_BYTES:
            logger.warning(f"⚠️ Media too large ({len(content)} bytes), skipping upload")
            return None
        
        logger.info(f"✅ Media downloaded successfully: {len(content)} bytes, type={content_type}")
        return content, content_type
    except Exception as e:
        logger.error(f"❌ Error downloading media: {e}", exc_info=True)
        return None


def _compress_image(content: bytes, media_type: Optional[str]) -> Optional[tuple[bytes, str]]:
    """Downsize and recompress image to keep WhatsApp-friendly size."""
    try:
        img = Image.open(io.BytesIO(content))
        img = img.convert("RGB")  # Ensure JPEG-compatible

        max_side = 1600
        w, h = img.size
        if max(w, h) > max_side:
            ratio = max_side / float(max(w, h))
            img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)

        target_bytes = 900_000  # ~0.9 MB target to stay well under Twilio limits
        quality = 85
        min_quality = 50
        best = None

        while quality >= min_quality:
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=quality, optimize=True)
            data = buf.getvalue()
            best = data
            if len(data) <= target_bytes:
                break
            quality -= 10

        if best:
            return best, "image/jpeg"
        return None
    except Exception as e:
        logger.warning(f"Image compression failed, using original: {e}")
        return None


def _extract_image_urls(text: str) -> List[str]:
    """Pick first few image URLs (Supabase public) from agent response."""
    if not text:
        return []
    urls = re.findall(r"https?://\S+", text)
    images: List[str] = []
    for u in urls:
        # Heuristic: only Supabase storage links or common image extensions
        lower = u.lower()
        if ("/storage/v1/object/" in lower) or lower.endswith(('.jpg', '.jpeg', '.png', '.webp')):
            images.append(u.rstrip(').,;'))
        if len(images) >= MAX_MEDIA_PER_MESSAGE:
            break
    return images


async def upload_to_supabase(path: str, content: bytes, content_type: str) -> bool:
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        logger.warning("Supabase credentials missing, cannot upload media")
        return False
    upload_url = f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_STORAGE_BUCKET}/{path}"
    headers = {
        "Content-Type": content_type,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "apikey": SUPABASE_SERVICE_KEY,
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(upload_url, content=content, headers=headers)
        if resp.status_code in (200, 201):
            logger.info(f"✅ Uploaded media to Supabase: {path}")
            return True
        logger.warning(f"Supabase upload failed ({resp.status_code}): {resp.text}")
        return False
    except Exception as e:
        logger.error(f"Error uploading to Supabase: {e}")
        return False


async def process_media(
    user_id: str,
    listing_uuid: str,
    media_url: str,
    media_type: Optional[str],
    message_sid: Optional[str] = None,
    media_sid: Optional[str] = None,
) -> Optional[str]:
    logger.info(f"🔄 Processing media: url={media_url[:80]}..., sid={message_sid}, media_sid={media_sid}")
    
    downloaded = await download_media(media_url, media_type, message_sid, media_sid)
    if not downloaded:
        logger.error(f"❌ Failed to download media from {media_url[:80]}")
        return None
    content, ctype = downloaded

    logger.info(f"🗜️ Compressing image ({len(content)} bytes)...")
    compressed = _compress_image(content, ctype)
    if compressed:
        content, ctype = compressed
        logger.info(f"✅ Compressed to {len(content)} bytes")

    storage_path = _build_storage_path(user_id, listing_uuid, ctype)
    logger.info(f"📤 Uploading to Supabase: {storage_path}")
    
    success = await upload_to_supabase(storage_path, content, ctype)
    if success:
        logger.info(f"✅ Media uploaded successfully: {storage_path}")
        return storage_path
    
    logger.error(f"❌ Failed to upload media to Supabase")
    return None


def get_conversation_history(phone_number: str) -> List[dict]:
    """Get conversation history for a phone number"""
    if phone_number not in conversation_store:
        return []
    
    session = conversation_store[phone_number]
    
    # Check if conversation expired
    if datetime.now() - session["last_activity"] > timedelta(minutes=CONVERSATION_TIMEOUT_MINUTES):
        logger.info(f"🕐 Conversation expired for {phone_number}, clearing history")
        del conversation_store[phone_number]
        return []
    
    return session["messages"]


def add_to_conversation_history(phone_number: str, role: str, content: str):
    """Add a message to conversation history"""
    if phone_number not in conversation_store:
        conversation_store[phone_number] = {
            "messages": [],
            "last_activity": datetime.now()
        }
    
    conversation_store[phone_number]["messages"].append({
        "role": role,
        "content": content,
        "timestamp": datetime.now().isoformat()
    })
    conversation_store[phone_number]["last_activity"] = datetime.now()
    
    # Keep only last 20 messages to prevent memory overflow
    if len(conversation_store[phone_number]["messages"]) > 20:
        conversation_store[phone_number]["messages"] = conversation_store[phone_number]["messages"][-20:]
    
    logger.info(f"💾 Conversation history updated for {phone_number}: {len(conversation_store[phone_number]['messages'])} messages")


def update_search_cache(phone_number: str, results: List[dict]):
    """Store last search results (for detail requests) in memory."""
    if phone_number not in conversation_store:
        conversation_store[phone_number] = {"messages": [], "last_activity": datetime.now()}
    conversation_store[phone_number]["search_cache"] = {
        "results": results,
        "timestamp": datetime.now().isoformat()
    }
    conversation_store[phone_number]["last_activity"] = datetime.now()
    logger.info(f"💾 Search cache stored for {phone_number}: {len(results)} results")


def get_search_cache(phone_number: str) -> Optional[List[dict]]:
    cache = conversation_store.get(phone_number, {}).get("search_cache")
    if not cache:
        return None
    return cache.get("results") if isinstance(cache.get("results"), list) else None


def parse_search_cache_block(text: str) -> tuple[str, Optional[List[dict]]]:
    """Strip [SEARCH_CACHE]{json} block from text and return remaining text and parsed results."""
    if not text:
        return text, None
    match = re.search(r"\[SEARCH_CACHE\](\{.*\})", text, flags=re.DOTALL)
    if not match:
        return text, None
    json_part = match.group(1)
    try:
        parsed = ast.literal_eval(json_part)
        if isinstance(parsed, dict) and isinstance(parsed.get("results"), list):
            stripped = text.replace(match.group(0), "").strip()
            return stripped, parsed.get("results")
    except Exception:
        logger.warning("Failed to parse SEARCH_CACHE block")
    stripped = text.replace(match.group(0), "").strip()
    return stripped, None


def clear_conversation_history(phone_number: str):
    """Clear conversation history for a phone number"""
    if phone_number in conversation_store:
        del conversation_store[phone_number]
        logger.info(f"🗑️ Conversation history cleared for {phone_number}")


def format_listing_detail(listing: dict) -> str:
    """Render a compact detail view for a single listing using cached search results."""
    title = listing.get("title") or "İlan"
    price = listing.get("price")
    location = listing.get("location") or "Belirtilmedi"
    condition = listing.get("condition") or "Belirtilmedi"
    category = listing.get("category") or "Belirtilmedi"
    listing_id = listing.get("id")
    owner_name = listing.get("user_name") or listing.get("owner_name")
    owner_phone = listing.get("user_phone") or listing.get("owner_phone")
    description = listing.get("description") or ""
    desc_short = description[:160] + ("..." if len(description or "") > 160 else "")

    lines = [title]
    if price is not None:
        lines.append(f"Fiyat: {price} TL")
    lines.append(f"Konum: {location}")
    lines.append(f"Durum: {condition}")
    lines.append(f"Kategori: {category}")
    if listing_id:
        lines.append(f"İlan ID: {listing_id}")
    if owner_name or owner_phone:
        parts = []
        if owner_name:
            parts.append(owner_name)
        if owner_phone:
            parts.append(owner_phone)
        lines.append("İlan sahibi: " + " | ".join(parts))
    if desc_short:
        lines.append(f"Açıklama: {desc_short}")

    signed_images = listing.get("signed_images") if isinstance(listing.get("signed_images"), list) else []
    imgs = signed_images[:3]
    if imgs:
        lines.append("Fotoğraflar:")
        lines.extend(imgs)
    else:
        lines.append("Fotoğraf yok")

    return "\n".join(lines)


def send_twilio_message(phone_number: str, body_text: str) -> None:
    """Send WhatsApp message via Twilio with length and media safeguards."""
    if not twilio_client:
        logger.warning("⚠️ Twilio not configured, response not sent")
        return

    media_urls = _extract_image_urls(body_text)

    # Twilio WhatsApp limit: body + media_url combined max 1600 chars
    MAX_WHATSAPP_LENGTH = 1600
    MEDIA_URL_OVERHEAD = len(media_urls) * 120  # Reserve 120 chars per media URL
    MAX_BODY_LENGTH = MAX_WHATSAPP_LENGTH - MEDIA_URL_OVERHEAD - 100  # Extra safety margin

    truncated_response = body_text
    if len(body_text) > MAX_BODY_LENGTH:
        logger.warning(
            f"⚠️ Response too long ({len(body_text)} chars), truncating to {MAX_BODY_LENGTH} (with {len(media_urls)} media)"
        )
        truncated_response = body_text[:MAX_BODY_LENGTH - 60] + "\n\n...(devamı için daha spesifik arama yapın)"

    message = twilio_client.messages.create(
        from_=f'whatsapp:{TWILIO_WHATSAPP_NUMBER}',
        body=truncated_response,
        media_url=media_urls if media_urls else None,
        to=f'whatsapp:{phone_number}'
    )
    logger.info(f"✅ Twilio message sent: {message.sid}")
# ================================================


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "Pazarglobal WhatsApp Bridge",
        "version": "3.0.0",
        "api_type": "Agent Backend (OpenAI Agents SDK)",
        "twilio_configured": bool(twilio_client),
        "agent_backend_url": AGENT_BACKEND_URL
    }


@app.post("/webhook/whatsapp")
async def whatsapp_webhook(
    request: Request,
    Body: str = Form(...),
    From: str = Form(...),
    To: str = Form(None),
    MessageSid: str = Form(None),
    NumMedia: int = Form(0),  # Number of media files (first index)
    MediaUrl0: str = Form(None),  # First media URL (kept for FastAPI schema)
    MediaContentType0: str = Form(None),  # First media content type (schema)
):
    """
    Twilio WhatsApp webhook endpoint
    
    Flow:
    1. Receive WhatsApp message from Twilio (text + optional media)
    2. Get conversation history for this phone number
    3. Send to Agent Backend (OpenAI Agents SDK with MCP tools)
    4. Store agent response in conversation history
    5. Send back via Twilio WhatsApp
    """
    form = await request.form()
    num_media = int(form.get("NumMedia", 0) or 0)
    media_keys = {k: v for k, v in form.items() if k.lower().startswith("media")}
    form_items = list(form.items())

    logger.info(f"📱 Incoming WhatsApp message from {From}: {Body}")
    logger.info(f"🔍 DEBUG - NumMedia: {num_media}, MediaUrl0: {MediaUrl0}, MediaContentType0: {MediaContentType0}")
    logger.info(f"🔍 DEBUG - MessageSid: {MessageSid}")
    logger.info(f"🧾 FORM MEDIA KEYS: {media_keys}")
    logger.info(f"🧾 FORM ITEMS (first 30): {form_items[:30]}")

    # Extract phone number early for history reuse
    phone_number = From.replace('whatsapp:', '')
    previous_history = get_conversation_history(phone_number)
    prev_draft_id, prev_media_paths = _extract_last_media_context(previous_history)

    # Check for media attachments (support multiple)
    media_items: List[tuple[str, Optional[str], Optional[str], Optional[str]]] = []
    for i in range(min(num_media, 10)):
        url = form.get(f"MediaUrl{i}")
        mtype = form.get(f"MediaContentType{i}")
        msid = form.get("MessageSid")
        # Twilio media SID is the last token of the URL
        media_sid = url.split("/")[-1] if url else None
        if url:
            media_items.append((url, mtype, msid, media_sid))

    if has_media := len(media_items) > 0:
        logger.info(f"🧾 MEDIA ITEMS PARSED: {media_items}")

    first_media_type = media_items[0][1] if has_media else None
    # Start with previous media paths (from earlier webhooks/messages)
    media_paths: List[str] = list(prev_media_paths) if prev_media_paths else []
    draft_listing_id: Optional[str] = prev_draft_id

    if has_media:
        logger.info(f"📸 Media attached count: {len(media_items)}")
        draft_listing_id = draft_listing_id or str(uuid.uuid4())
        logger.info(f"📋 Draft listing ID: {draft_listing_id}")
        uploaded_any = False

        for idx, (url, mtype, msid, media_sid) in enumerate(media_items):
            logger.info(f"📸 Processing media {idx+1}/{len(media_items)}: {url[:80]}...")
            uploaded_path = await process_media(phone_number, draft_listing_id, url, mtype, msid, media_sid)
            if uploaded_path:
                uploaded_any = True
                # Add to media_paths if not already there
                if uploaded_path not in media_paths:
                    media_paths.append(uploaded_path)
                logger.info(f"✅ Media uploaded: {uploaded_path}")
            else:
                logger.warning(f"Media upload failed for {url}")

        if uploaded_any and media_paths:
            media_note = f"[SYSTEM_MEDIA_NOTE] DRAFT_LISTING_ID={draft_listing_id} | MEDIA_PATHS={media_paths}"
            add_to_conversation_history(phone_number, "assistant", media_note)
        else:
            logger.warning("Media processing failed; continuing without attachment")
            # Optional: notify user about media failure

    # If no new media uploaded, still surface previous draft/media context to backend
    payload_media_paths = media_paths if media_paths else (prev_media_paths if prev_media_paths else None)
    payload_draft_id = draft_listing_id or prev_draft_id
    
    logger.info(f"📦 Sending to agent: draft_id={payload_draft_id}, media_count={len(payload_media_paths) if payload_media_paths else 0}")
    if payload_media_paths:
        logger.info(f"📸 Media paths being sent: {payload_media_paths}")

    # Short-circuit: detail request using cached search results
    lower_body = (Body or "").lower().strip()
    search_cache = get_search_cache(phone_number)
    detail_match = re.search(r"(\d+)\s*nolu\s*ilan[ıi]?\s*göster", lower_body)
    detail_idx: Optional[int] = None
    if detail_match:
        detail_idx = int(detail_match.group(1)) - 1
    elif search_cache and len(search_cache) == 1 and ("detay" in lower_body or "ilanı" in lower_body):
        detail_idx = 0

    if search_cache is not None and detail_idx is not None:
        if 0 <= detail_idx < len(search_cache):
            listing = search_cache[detail_idx]
            detail_text = format_listing_detail(listing)
            add_to_conversation_history(phone_number, "user", Body)
            add_to_conversation_history(phone_number, "assistant", detail_text)
            send_twilio_message(phone_number, detail_text)
            resp = MessagingResponse()
            return Response(content=str(resp), media_type="application/xml")
        else:
            warn_text = f"Bu aramada sadece {len(search_cache)} ilan var. 1-{len(search_cache)} arasından bir numara seçebilirsin."
            add_to_conversation_history(phone_number, "user", Body)
            add_to_conversation_history(phone_number, "assistant", warn_text)
            send_twilio_message(phone_number, warn_text)
            resp = MessagingResponse()
            return Response(content=str(resp), media_type="application/xml")

    try:
        user_message = Body

        # Get conversation history (previous messages only, NOT current message)
        conversation_history = get_conversation_history(phone_number)
        logger.info(f"📚 Conversation history for {phone_number}: {len(conversation_history)} messages")
        
        # Step 1: Call Agent Backend with conversation history + media URL
        # NOTE: current user_message is sent separately, NOT in history
        logger.info(f"🤖 Calling Agent Backend: {AGENT_BACKEND_URL}")
        agent_response = await call_agent_backend(
            user_message, 
            phone_number, 
            conversation_history,
            media_paths=payload_media_paths,
            media_type=first_media_type if payload_media_paths else None,
            draft_listing_id=payload_draft_id
        )
        
        if not agent_response:
            raise HTTPException(status_code=500, detail="No response from Agent Backend")
        
        logger.info(f"✅ Agent response: {agent_response[:100]}...")

        # Extract and store search cache (if present), and strip it from user-facing text
        agent_response, search_cache_results = parse_search_cache_block(agent_response)
        if search_cache_results:
            update_search_cache(phone_number, search_cache_results)
            logger.info(f"📦 Search cache captured with {len(search_cache_results)} results")
        
        # Step 2: Now add both user message and agent response to history
        add_to_conversation_history(phone_number, "user", user_message)
        add_to_conversation_history(phone_number, "assistant", agent_response)
        
        # Step 3: Send response back via Twilio WhatsApp
        send_twilio_message(phone_number, agent_response)
        
        # Return TwiML response (Twilio expects this)
        resp = MessagingResponse()
        return Response(content=str(resp), media_type="application/xml")
        
    except Exception as e:
        logger.error(f"❌ Error processing WhatsApp message: {str(e)}")
        logger.exception(e)
        
        # Send error message to user
        resp = MessagingResponse()
        resp.message("Üzgünüm, bir hata oluştu. Lütfen daha sonra tekrar deneyin.")
        return Response(content=str(resp), media_type="application/xml")


async def call_agent_backend(
    user_input: str, 
    user_id: str, 
    conversation_history: List[dict],
    media_paths: Optional[List[str]] = None,
    media_type: str = None,
    draft_listing_id: Optional[str] = None
) -> str:
    """
    Call Agent Backend (OpenAI Agents SDK with MCP tools)
    
    Args:
        user_input: User's message text
        user_id: User identifier (phone number)
        conversation_history: Previous messages in conversation
        media_paths: Optional list of uploaded storage paths
        media_type: Optional media content type (e.g., "image/jpeg")
        draft_listing_id: Optional UUID to keep storage paths and DB id aligned
        
    Returns:
        Agent's response text
    """
    if not AGENT_BACKEND_URL:
        logger.error("AGENT_BACKEND_URL not configured")
        return "Sistem yapılandırma hatası. Lütfen yönetici ile iletişime geçin."
    
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            # Call agent backend endpoint
            logger.info(f"🚀 Calling Agent Backend: {AGENT_BACKEND_URL}/agent/run")
            
            payload = {
                "user_id": user_id,
                "message": user_input,
                "conversation_history": conversation_history,  # Now includes full conversation context!
                "media_paths": media_paths,
                "media_type": media_type,
                "draft_listing_id": draft_listing_id,
            }
            
            logger.info(f"📦 Payload: user_id={user_id}, history_length={len(conversation_history)}")
            
            response = await client.post(
                f"{AGENT_BACKEND_URL}/agent/run",
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            
            result = response.json()
            logger.info(f"✅ Agent Backend response received")
            logger.info(f"   Intent: {result.get('intent', 'unknown')}")
            logger.info(f"   Success: {result.get('success', False)}")
            
            if not result.get("success"):
                logger.error(f"⚠️ Agent Backend returned success=false")
                return "İşlem başarısız oldu. Lütfen tekrar deneyin."
            
            response_text = result.get("response", "")
            if not response_text:
                logger.error("⚠️ Empty response from Agent Backend")
                return "Boş yanıt alındı. Lütfen tekrar deneyin."
            
            logger.info(f"✅ Response text: {response_text[:100]}...")
            return response_text
            
    except httpx.HTTPStatusError as e:
        logger.error(f"❌ Agent Backend HTTP error: {e.response.status_code}")
        try:
            error_detail = e.response.json()
            logger.error(f"   Error detail: {error_detail}")
        except:
            logger.error(f"   Response text: {e.response.text}")
        return "Agent servisi şu anda yanıt vermiyor. Lütfen daha sonra tekrar deneyin."
    except httpx.TimeoutException:
        logger.error("⏱️ Agent Backend timeout (120s)")
        return "İstek zaman aşımına uğradı. Lütfen tekrar deneyin."
    except Exception as e:
        logger.error(f"❌ Unexpected error calling Agent Backend: {str(e)}")
        logger.exception(e)
        return "Beklenmeyen bir hata oluştu."


@app.get("/health")
async def health_check():
    """Detailed health check"""
    return {
        "status": "healthy",
        "checks": {
            "agent_backend_url": AGENT_BACKEND_URL,
            "twilio_configured": "yes" if twilio_client else "no",
            "active_conversations": len(conversation_store)
        }
    }


@app.post("/conversation/clear/{phone_number}")
async def clear_conversation(phone_number: str):
    """Clear conversation history for a phone number (admin endpoint)"""
    clear_conversation_history(phone_number)
    return {"status": "cleared", "phone_number": phone_number}


@app.get("/conversation/{phone_number}")
async def get_conversation(phone_number: str):
    """Get conversation history for a phone number (debug endpoint)"""
    history = get_conversation_history(phone_number)
    return {
        "phone_number": phone_number,
        "message_count": len(history),
        "messages": history
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
