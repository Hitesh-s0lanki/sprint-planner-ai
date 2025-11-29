# API Documentation: `/api/chat`

## Endpoint

**POST** `/api/chat`

## Description

Streams chat responses from the AI agent in real-time. The endpoint accepts a user message and returns a streaming response in NDJSON (Newline-Delimited JSON) format, where each line contains incremental chunks of the agent's response.

## Request

### Headers

```
Content-Type: application/json
```

### Request Body

The request body must be a JSON object with the following structure:

```json
{
  "message": "string"
}
```

#### Request Schema

| Field     | Type     | Required | Description                                         |
| --------- | -------- | -------- | --------------------------------------------------- |
| `message` | `string` | Yes      | The user's message/question to send to the AI agent |

#### Example Request

```json
{
  "message": "What is a sprint in agile development?"
}
```

## Response

### Response Format

- **Content-Type**: `application/x-ndjson`
- **Format**: Streaming NDJSON (Newline-Delimited JSON)
- **Encoding**: UTF-8

### Response Headers

```
Content-Type: application/x-ndjson
Cache-Control: no-cache
Connection: keep-alive
X-Accel-Buffering: no
```

### Response Body

The response is streamed as NDJSON, where each line is a JSON object representing a chunk of the agent's response:

```json
{"content": "chunk 1"}
{"content": "chunk 2"}
{"content": "chunk 3"}
...
```

#### Response Schema (per line)

Each line in the stream is a JSON object with the following structure:

| Field     | Type     | Description                                            |
| --------- | -------- | ------------------------------------------------------ |
| `content` | `string` | Incremental chunk of text from the AI agent's response |

#### Example Response Stream

```
{"content": "A sprint"}
{"content": " is a"}
{"content": " time-boxed"}
{"content": " period"}
{"content": " in agile"}
{"content": " development..."}
```

**Note**: Each line contains only the **new** content chunk, not the accumulated response. The client should concatenate all chunks to build the complete response.

### Error Responses

#### 503 Service Unavailable

Occurs when the agent is not initialized or unavailable.

```json
{
  "detail": "Agent unavailable. Check server logs and OPENAI_API_KEY."
}
```

#### 500 Internal Server Error

Occurs when an error happens during streaming. The error is returned as a streamed response:

```
{"content": "Error: <error message>"}
```

## Example Usage

### cURL

```bash
curl -X POST "http://localhost:8000/api/chat" \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello, how are you?"}' \
  --no-buffer
```

### Python (using `httpx`)

```python
import httpx
import json

async with httpx.AsyncClient() as client:
    async with client.stream(
        "POST",
        "http://localhost:8000/api/chat",
        json={"message": "What is agile?"}
    ) as response:
        async for line in response.aiter_lines():
            if line:
                chunk = json.loads(line)
                print(chunk["content"], end="", flush=True)
```

### JavaScript (using `fetch`)

```javascript
async function streamChat(message) {
  const response = await fetch("http://localhost:8000/api/chat", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ message }),
  });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    const chunk = decoder.decode(value);
    const lines = chunk.split("\n").filter((line) => line.trim());

    for (const line of lines) {
      const data = JSON.parse(line);
      console.log(data.content);
    }
  }
}
```

## Notes

1. **Streaming**: This endpoint uses server-sent streaming. The client should read the response as a stream, not wait for the complete response.

2. **NDJSON Format**: Each line is a complete JSON object. Empty lines should be ignored.

3. **Content Chunks**: Each chunk contains only the new text since the last chunk. The client must concatenate chunks to build the full response.

4. **Agent Availability**: The agent must be initialized at server startup. If `OPENAI_API_KEY` is not set or the agent fails to initialize, requests will return a 503 error.

5. **Session Management**: This endpoint does not handle session management. For session-based conversations, use the endpoints in `/api/chat/session/*` or `/api/chat/message`.

## Related Endpoints

- `POST /api/chat/session/create` - Create a new chat session
- `POST /api/chat/message` - Send a message (non-streaming, with session support)
- `GET /api/chat/session/{session_id}/messages` - Retrieve messages from a session
