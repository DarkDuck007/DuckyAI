# Bale Messenger Bot API Specifications

Based on the reference implementations and documentation, Bale Messenger's Bot API is designed to mimic the Telegram Bot API. This allows developers to use familiar paradigms, such as long-polling, identical endpoint structures, and identical JSON response shapes.

## Base URL and Authentication

- **Base API URL:** `https://tapi.bale.ai`
- **Authentication:** All requests must include the bot's token in the URL path.
- **Endpoint Structure:** `https://tapi.bale.ai/bot<TOKEN>/<METHOD_NAME>`

## Response Format

The API returns JSON responses with a structure identical to Telegram:
```json
{
  "ok": true,
  "result": { ... },
  "description": "Error message if ok is false"
}
```

## Supported Methods

### 1. `getUpdates`
Used to receive incoming messages and events via long-polling.
- **Method:** `POST`
- **Payload:**
  - `offset` (integer/string): Identifier of the first update to be returned.
  - `timeout` (integer/string): Timeout in seconds for long polling.

### 2. `sendMessage`
Sends a text message to a specified chat.
- **Method:** `POST`
- **Payload:**
  - `chat_id` (string/integer): Unique identifier for the target chat.
  - `text` (string): Text of the message to be sent.

### 3. `editMessageText`
Edits the text of an already sent message.
- **Method:** `POST`
- **Payload:**
  - `chat_id` (string/integer): Unique identifier for the target chat.
  - `message_id` (string/integer): Identifier of the message to edit.
  - `text` (string): New text of the message.

### 4. `sendDocument`
Sends general files.
- **Method:** `POST` (Requires `multipart/form-data` for new file uploads)
- **Payload:**
  - `chat_id` (string/integer)
  - `document`: Either a specific `file_id` (string) to resend an existing file, or the multipart file stream to upload a new one.
  - `caption` (string, optional): Document caption.

### 5. `sendPhoto`
Sends images.
- **Method:** `POST` (Requires `multipart/form-data` for new file uploads)
- **Payload:**
  - `chat_id` (string/integer)
  - `photo`: Either a `file_id` (string) to resend an existing photo, or the multipart file stream.
  - `caption` (string, optional): Photo caption.

### 6. `getFile`
Gets basic info about a file and prepares it for downloading.
- **Method:** `POST`
- **Payload:**
  - `file_id` (string): ID of the file to retrieve.
- **Response:** Returns a file object containing a `file_path`.

### 7. File Downloading
Once a `file_path` is retrieved via `getFile`, the actual file binary can be downloaded from:
`https://tapi.bale.ai/file/bot<TOKEN>/<file_path>`

## Usage Example (Python)

Below is an example of an asynchronous wrapper for the Bale API based on the reference project. 
It uses the `requests` library in a background thread to stay non-blocking.

```python
import asyncio
import requests
from pathlib import Path

class BaleApi:
    def __init__(self, token: str, base_url: str = "https://tapi.bale.ai"):
        self._token = token
        self._base_url = base_url.rstrip("/")

    def _request_sync(self, method: str, data: dict = None, files: dict = None, timeout: int = 30):
        url = f"{self._base_url}/bot{self._token}/{method}"
        resp = requests.post(url, data=data, files=files, timeout=timeout)
        payload = resp.json()
        
        if not payload.get("ok"):
            raise RuntimeError(payload.get("description", f"{method} failed"))
        return payload["result"]

    async def request(self, method: str, data: dict = None, files: dict = None, timeout: int = 30):
        return await asyncio.to_thread(self._request_sync, method, data, files, timeout)

    async def get_updates(self, offset: int, timeout_seconds: int = 5):
        return await self.request(
            "getUpdates",
            data={"offset": str(offset), "timeout": str(timeout_seconds)},
            timeout=timeout_seconds + 15,
        )

    async def send_message(self, chat_id: int, text: str):
        return await self.request("sendMessage", data={"chat_id": str(chat_id), "text": text})

    async def send_document(self, chat_id: int, file_path: Path, caption: str = None):
        def _upload():
            data = {"chat_id": str(chat_id)}
            if caption:
                data["caption"] = caption
            # Safe ascii filenames prevent header issues in multipart form data
            with file_path.open("rb") as handle:
                files = {"document": (file_path.name.encode('ascii', 'ignore').decode(), handle, "application/octet-stream")}
                return self._request_sync(
                    "sendDocument",
                    data=data,
                    files=files,
                    timeout=1800,  # Extended timeout for large uploads
                )
        return await asyncio.to_thread(_upload)
```

## Implementation Notes & Best Practices
- **Protocol Parity:** Because Bale mimics the structure of the Telegram Bot API so closely, existing Telegram Bot libraries can often be adapted to work with Bale simply by changing the base endpoint from `api.telegram.org` to `tapi.bale.ai`.
- **Upload Timeouts:** For uploading large files to Bale, use extended timeouts (e.g., up to 1800 seconds). Upload servers may be slower or drop connections if strict timeouts are enforced.
- **Concurrency & Threads:** Network requests should be run asynchronously. If using standard synchronous HTTP clients (like `requests`), always offload the blocking calls to a separate thread mapping to avoid stalling the asynchronous bot event loop.
- **Error Handling:** Check `payload.get("ok")`. If `false`, read the `description` field to retrieve the Bale-specific API error trace.
- **File Names:** When performing multipart uploads, ensure filenames are ASCII-safe (`str.encode('ascii', 'ignore')`) to prevent `multipart/form-data` encoding errors during request transmission to the Bale servers.

## Bale-Specific API Extensions

While Bale is largely a clone of the Telegram Bot API, it includes a few unique endpoints tailored to its specific platform features:

### 1. Payment API
Bale supports a complete payment flow (in Iranian Rials - IRR) natively integrated into the messenger. It bypasses the need for standard bank gateways by directly using Bale's financial wallet.
- **`sendInvoice`:** Sends a payment request to the user.
  - Requires `provider_token`. For testing without actual money movement, you can use `@botfather`'s testing token: `WALLET-TEST-1111111111111111`.
  - Prices must be presented in INR/IRR (Iranian Rials).
- **`answerPreCheckoutQuery`:** Used to approve or deny the transaction right before it's finalized by the user. 
- **`inquireTransaction`:** A Bale-exclusive method not found in Telegram. It is used to query the status of a specific transaction directly.
  - **Payload:** `transaction_id` (string).
  - **Response:** Returns a `Transaction` object containing:
    - `status`: Transaction state (`pending`, `paid`, `failed`, `rejected`).
    - `amount`: Transaction amount in IRR.
    - `userID` and `createdAt` (unix timestamp).

### 2. User Review System (`askReview`)
Bale provides a native UI for bots to solicit user ratings and feedback.
- **Method:** `POST /askReview`
- **Payload:**
  - `user_id` (integer): The unique identifier of the user to poll.
  - `delay_seconds` (integer): Delay in seconds before presenting the review UI. 
- **Response:** Returns `True` on success. (Note: Only supported on modern client versions).

### 3. File ID Portability
Bale guarantees that `file_id` parameters can be universally reused across different bot tokens and instances without needing to be re-uploaded.

### 4. Limited File Storage
Bale guarantees the storage of files up to 50 MB. Videos and documents under this limit will reliably upload, but the current cap limits larger files (in comparison to Telegram's 2GB cap).
