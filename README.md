# 📱 PazarGlobal WhatsApp Bridge

**Twilio WhatsApp API ↔️ Agent Backend Bridge Service**

WhatsApp kullanıcılarını PazarGlobal AI Agent Backend'e bağlayan webhook servisi. Twilio WhatsApp Business API entegrasyonu ile kullanıcıların WhatsApp üzerinden ilan oluşturma, arama ve yönetme işlemlerini gerçekleştirmesini sağlar.

---

## 📋 İçindekiler

- [Mimari Genel Bakış](#-mimari-genel-bakış)
- [Özellikler](#-özellikler)
- [Kurulum](#-kurulum)
- [Railway Deployment](#-railway-deployment)
- [Twilio Konfigürasyonu](#-twilio-konfigürasyonu)
- [Media Handling](#-media-handling)
- [Conversation Management](#-conversation-management)
- [Environment Variables](#-environment-variables)
- [API Endpoints](#-api-endpoints)
- [Sorun Giderme](#-sorun-giderme)

---

## 🏗️ Mimari Genel Bakış

```
┌──────────────────────────────────────────────────────────────┐
│              PazarGlobal WhatsApp Bridge                     │
│          (Twilio ↔️ Agent Backend Köprüsü)                   │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  WhatsApp User                                               │
│       ↓                                                      │
│  Twilio WhatsApp API (+1 415 523 8886)                      │
│       ↓                                                      │
│  POST /webhook/whatsapp (This Service)                      │
│       ↓                                                      │
│  ┌─────────────────────────────────┐                        │
│  │  Conversation Store (In-Memory) │                        │
│  │  - 30 min timeout               │                        │
│  │  - User conversation history    │                        │
│  └─────────────────────────────────┘                        │
│       ↓                                                      │
│  Media Handling (if NumMedia > 0)                           │
│       ↓                                                      │
│  ┌─────────────────────────────────┐                        │
│  │  1. Download from Twilio        │                        │
│  │  2. Validate & Compress         │                        │
│  │  3. Upload to Supabase Storage  │                        │
│  └─────────────────────────────────┘                        │
│       ↓                                                      │
│  POST Agent Backend /agent/run                              │
│       ↓                                                      │
│  Agent Response                                              │
│       ↓                                                      │
│  Twilio API (Send WhatsApp Message)                         │
│       ↓                                                      │
│  WhatsApp User                                               │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

**Teknoloji Stack:**

- **Framework:** FastAPI
- **WhatsApp API:** Twilio WhatsApp Business
- **Storage:** Supabase Storage (product-images bucket)
- **Image Processing:** Pillow (PIL)
- **Deployment:** Railway
- **Language:** Python 3.11+

---

## ✨ Özellikler

### 1. **Twilio WhatsApp Webhook Handler**

- ✅ Incoming WhatsApp mesajlarını yakalama
- ✅ Form data parsing (Body, From, To, MessageSid)
- ✅ Media detection (NumMedia, MediaUrl0, MediaContentType0)
- ✅ Error handling & logging

### 2. **Conversation History Management**

- ✅ In-memory conversation store
- ✅ 30 dakikalık inactivity timeout
- ✅ User-based session tracking
- ✅ Automatic cleanup (expired conversations)

**Conversation Store Structure:**

```python
conversation_store = {
    "whatsapp:+905551234567": {
        "messages": [
            {"role": "user", "content": "iPhone satıyorum"},
            {"role": "assistant", "content": "Harika! Detayları alayım..."}
        ],
        "last_activity": datetime.now()
    }
}
```

### 3. **Media Handling (Fotoğraf Yönetimi)**

- ✅ Twilio'dan media download (auth ile)
- ✅ Image validation (type, size, format)
- ✅ Automatic compression (max 1600px, ~900KB target)
- ✅ Supabase Storage upload
- ✅ Path tracking with [SYSTEM_MEDIA_NOTE]
- ✅ Multi-media support (max 3 photos per message)

**Media Processing Pipeline:**

```
Twilio Media URL → Download (with auth)
                      ↓
                 Validate (image/*, max 10MB)
                      ↓
                 Compress (PIL: resize + quality)
                      ↓
                 Upload to Supabase Storage
                      ↓
                 Return storage path
                      ↓
                 Send to Agent Backend
```

### 4. **Agent Backend Integration**

- ✅ POST to `/agent/run` endpoint
- ✅ User ID mapping (phone → Supabase users)
- ✅ Media paths forwarding
- ✅ Conversation history sync
- ✅ Draft listing ID tracking

### 5. **User Profile Management**

- ✅ Phone number → Supabase profiles lookup
- ✅ User name extraction (for personalization)
- ✅ Automatic user context enrichment

---

## 🚀 Kurulum

### 1. Gereksinimler

- Python 3.11+
- Twilio Account (WhatsApp Business API)
- Supabase Account
- Agent Backend deployed

### 2. Dependencies Kurulumu

```bash
cd pazarglobal-whatsapp-bridge
pip install -r requirements.txt
```

**requirements.txt:**

```
fastapi
uvicorn[standard]
python-multipart
httpx
twilio
python-dotenv
Pillow
```

### 3. Environment Variables

`.env` dosyası oluşturun:

```env
# Agent Backend URL
AGENT_BACKEND_URL=https://pazarglobal-agent-backend-production.up.railway.app

# Supabase Edge Function (Traffic Controller)
EDGE_FUNCTION_URL=https://YOUR_PROJECT_REF.supabase.co/functions/v1/whatsapp-traffic-controller

# Twilio Credentials
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_WHATSAPP_NUMBER=+14155238886

# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=eyJhbGc...
SUPABASE_STORAGE_BUCKET=product-images

# Server
PORT=8080
```

### 4. Lokal Çalıştırma

```bash
python main.py
```

Server başlatılır: `http://localhost:8080`

### 5. Test

```bash
# Health check
curl http://localhost:8080

# Webhook test (Twilio simulator kullan)
# https://www.twilio.com/console/sms/whatsapp/sandbox
```

---

## 🚂 Railway Deployment

### 1. GitHub Repository

```bash
git init
git add .
git commit -m "Initial commit: WhatsApp Bridge"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/pazarglobal-whatsapp-bridge.git
git push -u origin main
```

### 2. Railway Project Setup

1. **Railway'e git:** <https://railway.app/new>
2. **"Deploy from GitHub repo"** seç
3. **Repository:** `pazarglobal-whatsapp-bridge`
4. Railway otomatik Python detect edecek

### 3. Environment Variables (Railway Dashboard)

**Variables tab → RAW Editor:**

```env
AGENT_BACKEND_URL=https://pazarglobal-agent-backend-production.up.railway.app
EDGE_FUNCTION_URL=https://YOUR_PROJECT_REF.supabase.co/functions/v1/whatsapp-traffic-controller
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_WHATSAPP_NUMBER=+14155238886
SUPABASE_URL=https://...
SUPABASE_SERVICE_KEY=eyJhbGc...
SUPABASE_STORAGE_BUCKET=product-images
PORT=8080
```

### 4. Deploy

- Railway otomatik build & deploy başlatır
- Build time: ~2-3 dakika
- Public URL: `https://pazarglobal-whatsapp-bridge-production.up.railway.app`

### 5. Doğrulama

```bash
curl https://your-railway-url.up.railway.app
```

Expected:

```json
{
  "status": "healthy",
  "service": "Pazarglobal WhatsApp Bridge"
}
```

---

## 📞 Twilio Konfigürasyonu

### 1. Twilio Console Setup

1. **Login:** <https://console.twilio.com>
2. **WhatsApp Sandbox:** Messaging → Try it out → WhatsApp

### 2. Webhook URL Ayarlama

**Sandbox Settings:**

- **When a message comes in:**

  ```
  https://your-railway-url.up.railway.app/webhook/whatsapp
  ```

- **Method:** POST
- **Save**

### 3. WhatsApp Test

1. WhatsApp ile Twilio sandbox numarasına mesaj gönderin: `+1 415 523 8886`
2. İlk mesaj: `join [your-sandbox-code]` (örn: "join happy-monkey")
3. Test mesajı: `merhaba`
4. AI agent'tan cevap almalısınız!

### 4. Production (WhatsApp Business API)

**Not:** Sandbox yerine production WhatsApp Business API kullanmak için:

- Twilio WhatsApp Business onayı gerekir
- Company verification
- Message templates approval
- Pricing: Usage-based

---

## 🖼️ Media Handling

### Media Download & Validation

**Supported Media Types:**

- ✅ `image/jpeg`
- ✅ `image/png`
- ✅ `image/webp`
- ❌ Videos (şimdilik desteklenmiyor)
- ❌ Documents (şimdilik desteklenmiyor)

**Size Limits:**

- Max file size: 10 MB
- Max media per message: 3 photos
- Compressed target: ~900 KB per image

### Image Compression Algorithm

```python
def _compress_image(content: bytes, media_type: str) -> bytes:
    # 1. Load image
    img = Image.open(io.BytesIO(content))
    img = img.convert("RGB")  # Ensure JPEG compatibility
    
    # 2. Resize (max 1600px on longest side)
    max_side = 1600
    if max(img.size) > max_side:
        ratio = max_side / float(max(img.size))
        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
    
    # 3. Compress with quality adjustment
    target_bytes = 900_000  # ~900KB
    quality = 85
    while len(output) > target_bytes and quality > 30:
        output = compress_jpeg(img, quality)
        quality -= 5
    
    return output
```

### Supabase Storage Upload

**Storage Path Format:**

```
{user_id}/{listing_uuid}/{random_uuid}.{ext}

Example:
905551234567/550e8400-e29b-41d4-a716-446655440000/abc123.jpg
```

**Upload Process:**

```python
# 1. Build storage path
path = f"{user_id}/{listing_uuid}/{uuid4()}.jpg"

# 2. Upload to Supabase Storage
supabase.storage.from_(bucket).upload(path, content)

# 3. Return path (not URL!)
return path  # Agent backend will handle signed URLs
```

### Draft Listing ID Tracking

**[SYSTEM_MEDIA_NOTE] Format:**

```
[SYSTEM_MEDIA_NOTE] DRAFT_LISTING_ID=550e8400-... | MEDIA_PATHS=['path1.jpg', 'path2.jpg'] | MEDIA_TYPE=image/jpeg
```

**Purpose:**

- Track photos across conversation turns
- Link photos to draft listings
- Accumulate multiple photo uploads

**Example Flow:**

```
User: [Sends photo 1]
Bridge: [SYSTEM_MEDIA_NOTE] DRAFT_ID=abc | MEDIA_PATHS=['photo1.jpg']

User: "Bir fotoğraf daha gönderiyorum" [Sends photo 2]
Bridge: [Extracts draft_id=abc] → [SYSTEM_MEDIA_NOTE] DRAFT_ID=abc | MEDIA_PATHS=['photo1.jpg', 'photo2.jpg']

User: "Yayınla"
Agent: insert_listing_tool(images=['photo1.jpg', 'photo2.jpg'])
```

---

## 💬 Conversation Management

### In-Memory Store

**Data Structure:**

```python
conversation_store: Dict[str, dict] = {
    "whatsapp:+905551234567": {
        "messages": [
            {"role": "user", "content": "iPhone sat"},
            {"role": "assistant", "content": "Fiyat?"},
            {"role": "user", "content": "25 bin"}
        ],
        "last_activity": datetime(2025, 12, 10, 14, 30)
    }
}
```

### Timeout & Cleanup

**Configuration:**

```python
CONVERSATION_TIMEOUT_MINUTES = 30
```

**Cleanup Logic:**

```python
def _cleanup_expired_conversations():
    now = datetime.now()
    expired = []
    for phone, data in conversation_store.items():
        if (now - data["last_activity"]) > timedelta(minutes=30):
            expired.append(phone)
    
    for phone in expired:
        del conversation_store[phone]
```

**Trigger:** Her webhook request'te cleanup çalışır.

### Conversation History Limits

```python
MAX_HISTORY_LENGTH = 20  # Son 20 mesaj

if len(history) > MAX_HISTORY_LENGTH:
    history = history[-MAX_HISTORY_LENGTH:]  # Keep last 20
```

**Neden?**

- Token limitleri (OpenAI API)
- Response time optimization
- Memory management

---

## 🔧 Environment Variables

| Variable | Gerekli | Açıklama | Örnek |
|----------|---------|----------|-------|
| `AGENT_BACKEND_URL` | ✅ | Agent Backend URL | `https://...railway.app` |
| `TWILIO_ACCOUNT_SID` | ✅ | Twilio Account SID | `AC123...` |
| `TWILIO_AUTH_TOKEN` | ✅ | Twilio Auth Token | `abc123...` |
| `TWILIO_WHATSAPP_NUMBER` | ✅ | Twilio WhatsApp number | `+14155238886` |
| `SUPABASE_URL` | ✅ | Supabase project URL | `https://xyz.supabase.co` |
| `SUPABASE_SERVICE_KEY` | ✅ | Supabase service key | `eyJhbGc...` |
| `SUPABASE_STORAGE_BUCKET` | ✅ | Storage bucket name | `product-images` |
| `PORT` | ❌ | Server port | `8080` |

---

## 🌐 API Endpoints

### **GET /**

Health check endpoint.

**Response:**

```json
{
  "status": "healthy",
  "service": "Pazarglobal WhatsApp Bridge",
  "version": "1.0.0"
}
```

---

### **GET /health**

Detailed health check with configuration status.

**Response:**

```json
{
  "status": "healthy",
  "checks": {
    "agent_backend_url": "configured",
    "twilio_configured": true,
    "supabase_configured": true
  }
}
```

---

### **POST /webhook/whatsapp**

Twilio WhatsApp webhook endpoint.

**Expected Form Data (from Twilio):**

```
Body: "Message text"
From: "whatsapp:+905551234567"
To: "whatsapp:+14155238886"
MessageSid: "SM123..."
NumMedia: "1"  (if media attached)
MediaUrl0: "https://api.twilio.com/..."
MediaContentType0: "image/jpeg"
```

**Processing Flow:**

1. Parse form data
2. Get/create conversation history
3. Download & process media (if any)
4. Call Agent Backend
5. Send response via Twilio
6. Return TwiML (empty response to Twilio)

**Response (TwiML):**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Response></Response>
```

---

## 🐛 Sorun Giderme

### 1. Twilio Webhook Çalışmıyor

**Semptom:** WhatsApp mesajı gönderiliyor ama cevap gelmiyor

**Kontroller:**

```bash
# Railway logs kontrol
# Dashboard → Deployments → View Logs

# Webhook URL doğru mu?
# Twilio Console → WhatsApp Sandbox → Settings

# Railway service running mi?
curl https://your-railway-url.up.railway.app
```

**Common Issues:**

- ❌ Webhook URL yanlış (typo)
- ❌ Railway service down
- ❌ Environment variables eksik

---

### 2. Media Upload Başarısız

**Semptom:** Fotoğraf gönderiliyor ama yüklenmiyor

**Kontroller:**

```bash
# Supabase Storage bucket var mı?
# Dashboard → Storage → product-images

# Service key doğru mu?
echo $SUPABASE_SERVICE_KEY

# Bucket RLS policies?
# product-images → private bucket olmalı
# service_role ile upload edilmeli
```

**Logs:**

```
📥 Downloading media from: https://api.twilio.com/...
📊 Download response: status=200, content-type=image/jpeg
✅ Media downloaded successfully: 245678 bytes
📤 Uploading to Supabase: path/to/image.jpg
✅ Media uploaded successfully
```

---

### 3. Conversation History Kayboluyor

**Semptom:** Agent önceki mesajları hatırlamıyor

**Sebep:** Conversation timeout (30 dakika)

**Çözüm:**

```python
# main.py
CONVERSATION_TIMEOUT_MINUTES = 60  # Artır
```

---

### 4. Agent Backend Connection Error

**Semptom:** "Agent backend unavailable"

**Kontroller:**

```bash
# Agent Backend çalışıyor mu?
curl https://agent-backend-url.railway.app

# AGENT_BACKEND_URL doğru mu?
echo $AGENT_BACKEND_URL

# Network issue?
# Railway → Bridge → Agent Backend connection test
```

---

### 5. Twilio Authentication Failed

**Semptom:** Media download 401/403 error

**Çözüm:**

```python
# main.py - download_media function
auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# Environment variables kontrol
echo $TWILIO_ACCOUNT_SID
echo $TWILIO_AUTH_TOKEN
```

---

## 🎯 Gelecek Özellikler

### Phase 1: Persistent Conversation Store (Redis) 🔄

**Timeline:** 1 hafta

**Neden?**

- In-memory store Railway restart'ta kaybolur
- Multi-instance deployment için shared state gerekli

**Implementation:**

```python
import redis

redis_client = redis.from_url(os.getenv("REDIS_URL"))

def get_conversation(phone: str):
    data = redis_client.get(f"conv:{phone}")
    return json.loads(data) if data else {"messages": []}

def save_conversation(phone: str, messages: list):
    redis_client.setex(
        f"conv:{phone}",
        timedelta(hours=24),  # TTL
        json.dumps({"messages": messages})
    )
```

**Railway Redis Add-on:**

- Railway Dashboard → Add Plugin → Redis
- Auto-provision & REDIS_URL inject

---

### Phase 2: Voice Message Support 🎤

**Timeline:** 2 hafta

**Features:**

- Twilio audio download
- OpenAI Whisper transcription
- Text-to-Speech response (optional)

**Flow:**

```
WhatsApp Voice → Twilio → Bridge download
                              ↓
                    OpenAI Whisper API
                              ↓
                    Transcribed text → Agent Backend
```

---

### Phase 3: Rich Media Responses 📸

**Timeline:** 1 hafta

**Features:**

- Send images from search results
- Product photo previews
- Signed URL generation

**Example:**

```python
# Generate signed URL for listing image
url = supabase.storage.from_("product-images").create_signed_url(path, 300)

# Send via Twilio
twilio_client.messages.create(
    from_=TWILIO_WHATSAPP_NUMBER,
    to=user_phone,
    body="İşte ilan fotoğrafı:",
    media_url=[url]
)
```

---

### Phase 4: Rate Limiting & Security 🔐

**Timeline:** 1 hafta

**Features:**

- User-based rate limiting (10 msg/min)
- Spam detection
- Blocked users list
- Audit logging

---

### Phase 5: Multi-Language Support 🌍

**Timeline:** 2 hafta

**Languages:**

- Turkish (default)
- English
- Arabic

**Detection:**

```python
# Auto-detect from first message
language = detect_language(message)
user_context["language"] = language
```

---

## 📚 Kaynaklar

- **Twilio WhatsApp Docs:** <https://www.twilio.com/docs/whatsapp>
- **FastAPI Docs:** <https://fastapi.tiangolo.com>
- **Supabase Storage Docs:** <https://supabase.com/docs/guides/storage>
- **Railway Docs:** <https://docs.railway.app>

---

## 📝 Changelog

### v1.0.0 (Aralık 2025)

- ✅ Twilio WhatsApp webhook integration
- ✅ In-memory conversation store (30 min timeout)
- ✅ Media handling (download, compress, upload)
- ✅ User profile mapping (phone → Supabase)
- ✅ Agent Backend integration
- ✅ Draft listing ID tracking
- ✅ Multi-media support (max 3 photos)
- ✅ Automatic image compression
- ✅ SYSTEM_MEDIA_NOTE format

---

## 👨‍💻 Geliştirici Notları

### Code Structure

```
pazarglobal-whatsapp-bridge/
├── main.py                      # FastAPI app + webhook handler
├── requirements.txt             # Dependencies
├── runtime.txt                  # Python version
├── railway.json                 # Railway config
└── README.md                    # This file
```

### Key Functions

**1. Webhook Handler:**

```python
@app.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request):
    # Parse Twilio form data
    # Handle media
    # Call agent backend
    # Send response
```

**2. Media Processing:**

```python
async def download_media(url, type, sid, media_sid)
def _compress_image(content, media_type)
async def _upload_to_supabase(content, path)
```

**3. Conversation Management:**

```python
def get_conversation_history(phone)
def save_conversation(phone, messages)
def _cleanup_expired_conversations()
```

### Development Tips

```bash
# Local run with hot reload
uvicorn main:app --reload --port 8080

# Test with ngrok (for Twilio webhook testing)
ngrok http 8080
# Use ngrok URL as Twilio webhook

# Check logs
# Railway: Dashboard → Logs
# Local: Terminal output
```

---

## 🤝 Katkıda Bulunma

Bu proje aktif geliştirme aşamasında.

---

## 📄 Lisans

Private project - PazarGlobal

---

**Son Güncelleme:** 10 Aralık 2025  
**Versiyon:** 1.0.0  
**Durum:** Production Ready
