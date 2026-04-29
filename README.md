# Google Sheets Tracker with Streamlit Cloud

This project is a multipage Streamlit tracker connected to Google Sheets.

## Pages

- Dashboard
- Add Record
- Records
- Settings
- Google Sheet Updater

## Run locally

```bash
streamlit run app.py
```

## Streamlit Cloud secrets

Add the following values in your app secrets.
Prefer `GOOGLE_SHEET_ID` or `GOOGLE_SHEET_URL` because they do not require the Google Drive API:

```toml
GOOGLE_SHEET_NAME = "your-sheet-name"
GOOGLE_SHEET_ID = "your-google-sheet-id"
GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/your-google-sheet-id/edit#gid=0"

[gcp_service_account]
type = "service_account"
project_id = "your-project-id"
private_key_id = "your-private-key-id"
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "your-service-account@your-project.iam.gserviceaccount.com"
client_id = "your-client-id"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/..."
```

## Notes

- The app reads from the first sheet (`sheet1`) by default.
- If your Google Sheet column names are already present in row 1, the app uses them automatically.
- The `Google Sheet Updater` page imports `CSV` and `Excel` files and appends their rows into the `QA_Log` worksheet.
- You can customize pages and sheet structure based on your tracker fields.
