# 🚀 Pazarglobal WhatsApp Bridge - Deployment Guide

## Step 1: GitHub Repository Setup

### Create New GitHub Repo
1. Go to: https://github.com/new
2. **Repository name**: `pazarglobal-whatsapp-bridge`
3. **Description**: `WhatsApp webhook bridge for OpenAI Agent Builder - Pazarglobal project`
4. **Visibility**: Private (veya Public)
5. **DO NOT initialize** with README (we already have files)
6. Click **Create repository**

### Push Local Code to GitHub
```bash
cd "c:\Users\emrah badas\OneDrive\Desktop\pzarglobal mcpp\pazarglobal-whatsapp-bridge"

# Add remote (replace YOUR_USERNAME with your GitHub username)
git remote add origin https://github.com/emrahbadas00-lgtm/pazarglobal-whatsapp-bridge.git

# Push to GitHub
git branch -M main
git push -u origin main
```

---

## Step 2: Railway Deployment

### Create New Railway Project
1. Go to: https://railway.app/new
2. Click **Deploy from GitHub repo**
3. Select: `pazarglobal-whatsapp-bridge`
4. Railway will auto-detect Python and use `railway.json` config

### Set Environment Variables in Railway
Go to: Variables tab → Add Variables

```env
OPENAI_API_KEY=sk-proj-...your-key...
OPENAI_WORKFLOW_ID=wf_691884cc7e6081908974fe06852942af0249d08cf5054fdb
TWILIO_ACCOUNT_SID=AC...your-sid...
TWILIO_AUTH_TOKEN=...your-token...
TWILIO_WHATSAPP_NUMBER=+14155238886
```

**How to get these values:**

#### OPENAI_API_KEY
1. Go to: https://platform.openai.com/api-keys
2. Create new secret key
3. Copy immediately (won't show again)

#### OPENAI_WORKFLOW_ID
- Already in N8N config: `wf_691884cc7e6081908974fe06852942af0249d08cf5054fdb`
- OR check Agent Builder workflow settings

#### TWILIO Credentials
1. Go to: https://console.twilio.com
2. Dashboard → Account Info
3. Copy: Account SID, Auth Token
4. WhatsApp number from: Messaging → Try it out → WhatsApp

### Deploy
1. Click **Deploy**
2. Wait for build to complete (~2-3 minutes)
3. Railway will assign a URL: `https://pazarglobal-whatsapp-bridge-production.up.railway.app`

---

## Step 3: Twilio Webhook Configuration

### Update Twilio Webhook URL
1. Go to: https://console.twilio.com/us1/develop/sms/try-it-out/whatsapp-learn
2. Find **Sandbox settings**
3. Set **WHEN A MESSAGE COMES IN** webhook:
   ```
   https://your-railway-url.up.railway.app/webhook/whatsapp
   ```
4. Method: **POST**
5. Save

### Test WhatsApp Connection
1. Send WhatsApp message to Twilio sandbox number: `+1 415 523 8886`
2. First message: Join code (e.g., "join [your-code]")
3. Then test: "merhaba"
4. Should get response from AI agent

---

## Step 4: Verification

### Check Railway Logs
Railway dashboard → Deployments → View logs

Expected logs:
```
📱 Incoming WhatsApp message from whatsapp:+905551234567: merhaba
🤖 Calling OpenAI Agent Builder workflow: wf_...
✅ Agent response: Merhaba! Size nasıl yardımcı...
📤 Sending WhatsApp response to +905551234567
✅ Twilio message sent: SM...
```

### Test Health Endpoint
```bash
curl https://your-railway-url.up.railway.app/health
```

Expected response:
```json
{
  "status": "healthy",
  "checks": {
    "openai_key": "configured",
    "twilio_configured": "yes",
    "workflow_id": "wf_691884cc7e6081908974fe06852942af0249d08cf5054fdb"
  }
}
```

---

## Step 5: Testing Flow

### End-to-End Test
1. **Send WhatsApp**: "laptop aramak istiyorum"
2. **Expected Flow**:
   - Twilio receives message
   - Twilio POST to Railway webhook
   - Railway calls OpenAI Agent Builder
   - Agent processes with MCP tools (search_listings)
   - Agent returns response
   - Railway sends response via Twilio
   - User receives WhatsApp message

3. **Check Logs**:
   - Railway logs show all steps
   - Twilio logs show message delivery
   - OpenAI dashboard shows API calls

---

## 🎯 Architecture Overview

```
┌─────────────┐
│ WhatsApp    │
│ User        │
└──────┬──────┘
       │ Message: "laptop aramak istiyorum"
       ↓
┌─────────────────────────────┐
│ Twilio WhatsApp API         │
│ +1 415 523 8886             │
└──────┬──────────────────────┘
       │ POST /webhook/whatsapp
       ↓
┌─────────────────────────────┐
│ Railway Server              │
│ pazarglobal-whatsapp-bridge │
│ FastAPI                     │
└──────┬──────────────────────┘
       │ POST /v1/responses
       ↓
┌─────────────────────────────┐
│ OpenAI Agent Builder        │
│ Workflow ID: wf_...         │
│ - RouterAgent               │
│ - SearchProductAgent        │
│ - etc.                      │
└──────┬──────────────────────┘
       │ Uses MCP Tools
       ↓
┌─────────────────────────────┐
│ MCP Server (Railway)        │
│ pazarglobal-production      │
│ search_listings_tool        │
│ update_listing_tool         │
│ etc.                        │
└──────┬──────────────────────┘
       │ Queries Database
       ↓
┌─────────────────────────────┐
│ Supabase PostgreSQL         │
│ listings, users, etc.       │
└─────────────────────────────┘
       ↑
       │ Returns results
       │
   (Response flows back up the chain)
       │
       ↓
┌─────────────┐
│ WhatsApp    │
│ User        │
│ Receives:   │
│ "3 laptop   │
│ buldum..."  │
└─────────────┘
```

---

## 🔧 Troubleshooting

### Issue: "OPENAI_API_KEY not configured"
**Cause**: Environment variable missing in Railway  
**Fix**: Add variable in Railway dashboard

### Issue: No response from OpenAI
**Cause**: Workflow ID incorrect or workflow inactive  
**Fix**: 
1. Check workflow ID in Agent Builder
2. Ensure workflow is active
3. Test with Agent Builder playground

### Issue: Twilio webhook not triggering
**Cause**: URL incorrect or Railway not deployed  
**Fix**:
1. Verify Railway URL is live: `curl https://your-url/health`
2. Check Twilio webhook URL ends with `/webhook/whatsapp`
3. Ensure Railway deployment succeeded

### Issue: "permission denied" errors
**Cause**: Twilio credentials incorrect  
**Fix**: Verify TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN

---

## 📊 Monitoring

### Railway Dashboard
- View real-time logs
- Check CPU/Memory usage
- Monitor request count

### Twilio Console
- Message logs
- Webhook request logs
- Error reports

### OpenAI Dashboard
- API usage
- Request logs
- Cost tracking

---

## 💰 Cost Estimates

### Railway (Free Tier)
- ✅ 500 hours/month free
- ✅ $5 credit/month
- This server: ~1-2 hours/day = **FREE**

### Twilio
- WhatsApp messages: $0.005/message
- ~1000 messages/month = **$5/month**

### OpenAI
- Agent Builder API: Variable based on usage
- Estimate: $10-50/month depending on volume

**Total**: ~$15-60/month

---

## 🎉 Next Steps After Deployment

1. ✅ Test WhatsApp flow end-to-end
2. ✅ Update Agent Builder agents with tools
3. ✅ Configure RouterAgent with updated instructions
4. ✅ Test all agent intents (create, search, update, delete)
5. ✅ Monitor Railway logs for errors
6. ✅ Set up alerts for failures
7. ✅ Document production WhatsApp number

---

## 🔗 Related Resources

- [Twilio WhatsApp Docs](https://www.twilio.com/docs/whatsapp)
- [OpenAI Agent Builder Docs](https://platform.openai.com/docs/guides/agent-builder)
- [Railway Docs](https://docs.railway.app)
- [MCP Server Repo](https://github.com/emrahbadas00-lgtm/Pazarglobal)

---

## ✅ Deployment Checklist

- [ ] GitHub repo created and pushed
- [ ] Railway project created and connected
- [ ] All environment variables set in Railway
- [ ] Railway deployment successful
- [ ] Health endpoint returns 200 OK
- [ ] Twilio webhook URL updated
- [ ] WhatsApp sandbox joined
- [ ] Test message sent and received
- [ ] Railway logs show successful flow
- [ ] OpenAI Agent Builder responding
- [ ] MCP tools being called correctly

---

**Status**: Ready to deploy! Follow steps 1-5 above. 🚀
