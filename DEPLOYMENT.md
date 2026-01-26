# 🚀 Deployment Guide

This guide walks you through deploying the Vehicle Appraisal Pre-Check application to GitHub and Render.com.

## 📋 Prerequisites

- GitHub account
- Render.com account (free tier available)
- Supabase account with:
  - Database set up (run migrations from `migrations/` folder)
  - Storage bucket named `appraisal-artifacts` created
- OpenAI API key

---

## 1️⃣ Push to GitHub

### Step 1: Create GitHub Repository

1. Go to [GitHub](https://github.com/new)
2. Create a new repository (e.g., `vehicle-appraisal-pre-check`)
3. **Do NOT** initialize with README, .gitignore, or license (we already have these)
4. Copy the repository URL (e.g., `https://github.com/yourusername/vehicle-appraisal-pre-check.git`)

### Step 2: Add Remote and Push

Run these commands in the `vehicle-appraisal-app` directory:

```bash
# Add GitHub remote (replace with your repository URL)
git remote add origin https://github.com/yourusername/vehicle-appraisal-pre-check.git

# Push to GitHub
git branch -M main
git push -u origin main
```

**Note**: If you haven't set up GitHub authentication, you may need to:
- Use a Personal Access Token (Settings → Developer settings → Personal access tokens)
- Or use SSH: `git remote add origin git@github.com:yourusername/vehicle-appraisal-pre-check.git`

---

## 2️⃣ Deploy to Render.com

### Step 1: Connect GitHub to Render

1. Go to [Render Dashboard](https://dashboard.render.com)
2. Click **"New +"** → **"Blueprint"**
3. Connect your GitHub account if not already connected
4. Select the repository: `vehicle-appraisal-pre-check`
5. Render will detect `render.yaml` automatically

### Step 2: Configure Environment Variables

Before deploying, you need to set environment variables in Render. The `render.yaml` file will create two services, but you'll need to add secrets manually:

#### For `vehicle-appraisal-api` service:

Go to the service settings → Environment → Add the following:

| Key | Value | Notes |
|-----|-------|-------|
| `SUPABASE_URL` | `https://xxx.supabase.co` | Your Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | `xxx` | From Supabase Settings → API |
| `OPENAI_API_KEY` | `sk-xxx` | Your OpenAI API key |

**Note**: These are marked as `sync: false` in `render.yaml`, so you must set them manually.

#### For `vehicle-appraisal-ui` service:

No additional environment variables needed (API_BASE_URL is auto-configured via `fromService`).

### Step 3: Deploy

1. Click **"Apply"** in the Render dashboard
2. Render will:
   - Create both services (API and UI)
   - Build Docker images
   - Deploy to free tier
3. Wait for deployment to complete (~5-10 minutes for first build)

### Step 4: Verify Deployment

Once deployed, you'll get URLs like:
- API: `https://vehicle-appraisal-api.onrender.com`
- UI: `https://vehicle-appraisal-ui.onrender.com`

Test the health check:
```bash
curl https://vehicle-appraisal-api.onrender.com/healthz
```

---

## 3️⃣ Post-Deployment Setup

### Database Migrations

Make sure you've run all migrations in Supabase SQL Editor (in order):
1. `migrations/001_core.sql` - Core schema
2. `migrations/002_rag_embeddings.sql` - Vector search
3. `migrations/003_short_ids.sql` - Short IDs

### Storage Bucket

Create a storage bucket in Supabase:
- Name: `appraisal-artifacts`
- Public: No (private bucket)
- File size limit: Set as needed

### CORS Configuration

The API service automatically configures CORS to allow requests from the UI service. If you need to add additional origins, update the `CORS_ORIGINS` environment variable in the API service.

---

## 4️⃣ Free Tier Considerations

Render's free tier has some limitations:

- **Spin-down**: Services spin down after 15 minutes of inactivity
- **Cold starts**: First request after spin-down may take 30-60 seconds
- **Build time**: Limited build minutes per month
- **Bandwidth**: Limited bandwidth per month

**Recommendations**:
- Use a paid tier for production workloads
- Consider using Render's "Always On" feature (paid) to prevent spin-downs
- Monitor usage in Render dashboard

---

## 5️⃣ Troubleshooting

### Build Failures

1. Check build logs in Render dashboard
2. Verify Dockerfiles are correct
3. Ensure all dependencies are in `requirements.txt`

### Service Not Starting

1. Check service logs in Render dashboard
2. Verify environment variables are set correctly
3. Test health check endpoint: `/healthz`

### Database Connection Issues

1. Verify `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are correct
2. Check Supabase project is active
3. Verify network access (Supabase allows all IPs by default)

### CORS Errors

1. Verify `CORS_ORIGINS` includes your UI service URL
2. Check API service logs for CORS-related errors
3. Ensure `fromService` reference in `render.yaml` is correct

---

## 6️⃣ Updating Deployment

To update your deployment:

```bash
# Make your changes
git add .
git commit -m "Your changes"
git push origin main
```

Render will automatically detect the push and trigger a new deployment.

---

## 📚 Additional Resources

- [Render Documentation](https://render.com/docs)
- [Render Blueprint Spec](https://render.com/docs/blueprint-spec)
- [Supabase Documentation](https://supabase.com/docs)
- [Project README](README.md)

---

## ✅ Deployment Checklist

- [ ] Code pushed to GitHub
- [ ] GitHub repository connected to Render
- [ ] Environment variables set in Render
- [ ] Database migrations run in Supabase
- [ ] Storage bucket created in Supabase
- [ ] Both services deployed successfully
- [ ] Health checks passing
- [ ] UI accessible and can connect to API

---

**Need Help?** Check the [README](README.md) or open an issue on GitHub.
