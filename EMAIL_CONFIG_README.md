# 📧 Email Notification Setup

To enable automatic email notifications when an order is ready for collection or times out, you need to configure the email settings in `app.py`.

## Steps to Configure:

1.  **Open `app.py`** and locate the "Email Configuration" section near the top (around lines 10-15).
2.  **Update the following variables**:
    *   `SENDER_EMAIL`: Enter your Gmail address (or other provider).
    *   `SENDER_PASSWORD`: Enter your **App Password** (NOT your login password).
        *   *For Gmail:* Go to Google Account > Security > 2-Step Verification > App Passwords. Generate a new one.

```python
# specific lines in app.py
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = "your-actual-email@gmail.com"
SENDER_PASSWORD = "your-generated-app-password"
```

## How it Works:

1.  **Staff Approval**: When staff clicks "Ready for Collection" on the dashboard.
2.  **Email Sent**: An email is automatically sent to the user notifying them to collect the order within 20 seconds.
3.  **Timer Starts**: A 20-second timer runs in the background.
4.  **Timeout**: If not collected (delivered) in 20s, the order status reverts to "Paid" (Missed) or "Cancelled" (after 2 attempts), and another email is sent.

## Troubleshooting:

*   **"Bypassing email..." in logs**: This means you haven't replaced the placeholder email in `app.py` yet.
*   **Connection Errors**: Check your internet connection and ensure 2-Step Verification is enabled if using Gmail.
