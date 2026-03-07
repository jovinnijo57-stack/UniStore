# 📧 Email Notification Setup

To enable automatic email notifications when an order is ready for collection or times out, you need to configure the email settings in `app.py`.

## Steps to Configure:

### Option A: Gmail SMTP (Recommended for simplicity)
1.  **Open `app.py`** and locate the "Email Configuration" section.
2.  **Update the following variables** (or set them as Environment Variables on Render/Railway):
    *   `SENDER_EMAIL`: Your Gmail address.
    *   `SENDER_PASSWORD`: Your **App Password** (NOT your login password).
        *   *For Gmail:* Go to Google Account > Security > 2nd-Step Verification > App Passwords. Generate a new one.

### Option B: Brevo API (Higher reliability for production)
1.  Create a free account at [Brevo (Sendinblue)](https://www.brevo.com/).
2.  Get your **SMTP API Key** from Settings > SMTP & API.
3.  Add it as an Environment Variable:
    *   Key: `BREVO_API_KEY`
    *   Value: `your-api-key-here`

## How it Works:
The app is now "Universal". It will first try to send via **Brevo API** (if the key exists). If that fails or the key is missing, it will automatically fallback to **Gmail SMTP**.

