# Event Streaming API Documentation

## Overview

The event streaming API provides real-time updates during the stage completion process. When a user completes stage 8 (the final stage), the system automatically triggers stage completion, which includes project creation, document updates, team syncing, sprint planning, and narrative section generation. All these operations stream events in real-time to the frontend.

## When Event Streaming Occurs

Event streaming is automatically triggered when:

- **Stage 8 is completed** (the final stage in the workflow)
- The system detects that `next_stage > 8`, indicating all stages are done
- The stage completion process begins automatically

**Note:** This effectively happens at "stage 9" - after stage 8 completion.

## Endpoint

### POST `/api/streaming`

**Content-Type:** `application/json`  
**Response Type:** `application/x-ndjson` (Newline Delimited JSON)

### Request Body

```typescript
{
  connection_status: "started" | "active" | "events_streaming" | "events_completed" | "error" | "disactive",
  session_id: string,
  user_id?: string,
  user_message?: string,
  idea_state_stage: number, // 0-8 (8 is the final stage)
  user_preferences?: {
    user_id?: string,
    user_name?: string,
    user_email?: string
  },
  event?: {
    event_type?: string,
    event_status?: "started" | "completed"
  }
}
```

### Example Request (Stage 8 Completion)

```json
{
  "connection_status": "active",
  "session_id": "session_123",
  "user_id": "user_456",
  "user_message": "I agree with the constraints",
  "idea_state_stage": 8,
  "user_preferences": {
    "user_id": "user_456",
    "user_name": "John Doe",
    "user_email": "john@example.com"
  }
}
```

## Response Format

The API streams multiple `ChatResponse` objects in NDJSON format (one per line). Each line is a complete JSON object.

### ChatResponse Structure

```typescript
{
  connection_status: "started" | "active" | "events_streaming" | "events_completed" | "error" | "disactive",
  messages?: Array<{
    role: string,
    content: string,
    metadata?: object
  }>,
  response_content?: string,
  formatted_output?: object,
  error_message?: string,
  idea_state_stage: number,
  event?: {
    event_type: "team_members_synced" | "project_created" | "sources_updated" | "sprint_plan_generated" | "narrative_sections_started" | "completed",
    event_status: "started" | "completed",
    project_id?: string  // Included in the final "completed" event
  }
}
```

## Event Types and Sequence

When stage 8 completes, the following events are streamed in order:

### 1. Team Members Synced

```json
{
  "connection_status": "events_streaming",
  "event": {
    "event_type": "team_members_synced",
    "event_status": "started"
  },
  "idea_state_stage": 8
}
```

```json
{
  "connection_status": "events_streaming",
  "event": {
    "event_type": "team_members_synced",
    "event_status": "completed"
  },
  "idea_state_stage": 8
}
```

**Note:** Team members are loaded from the global idea state, synced with the database (created if needed), and then the project is created with these team members.

### 2. Project Created

```json
{
  "connection_status": "events_streaming",
  "event": {
    "event_type": "project_created",
    "event_status": "started"
  },
  "idea_state_stage": 8
}
```

```json
{
  "connection_status": "events_streaming",
  "event": {
    "event_type": "project_created",
    "event_status": "completed"
  },
  "idea_state_stage": 8
}
```

**Note:** Project is created with the lead user and synced team members.

### 3. Sources Updated (if documents exist)

```json
{
  "connection_status": "events_streaming",
  "event": {
    "event_type": "sources_updated",
    "event_status": "started"
  },
  "idea_state_stage": 8
}
```

```json
{
  "connection_status": "events_streaming",
  "event": {
    "event_type": "sources_updated",
    "event_status": "completed"
  },
  "idea_state_stage": 8
}
```

**Note:** All documents associated with the session are updated with the newly created project_id. This event only occurs if documents exist for the session.

### 4. Sprint Plan Generated

```json
{
  "connection_status": "events_streaming",
  "event": {
    "event_type": "sprint_plan_generated",
    "event_status": "started"
  },
  "idea_state_stage": 8
}
```

```json
{
  "connection_status": "events_streaming",
  "event": {
    "event_type": "sprint_plan_generated",
    "event_status": "completed"
  },
  "idea_state_stage": 8
}
```

**Note:** A full 4-week sprint plan is generated and saved as tasks in the database with proper dates and assignments.

### 5. Narrative Sections Started (Background Job)

```json
{
  "connection_status": "events_streaming",
  "event": {
    "event_type": "narrative_sections_started",
    "event_status": "started"
  },
  "idea_state_stage": 8
}
```

**Note:** Narrative sections generation runs in the background. Only the "started" event is sent. The job continues asynchronously and does not block the completion flow.

### 6. Final Completion

```json
{
  "connection_status": "events_streaming",
  "event": {
    "event_type": "completed",
    "event_status": "completed",
    "project_id": "550e8400-e29b-41d4-a716-446655440000"
  },
  "idea_state_stage": 8
}
```

**Note:** The final "completed" event includes the `project_id` field, which contains the UUID of the newly created project. This allows the frontend to immediately navigate to or display the project.

### 7. Events Completed

```json
{
  "connection_status": "events_completed",
  "idea_state_stage": 8,
  "response_content": "All stages completed. Project created successfully."
}
```

## Complete Example Response Stream

```
{"connection_status":"events_streaming","event":{"event_type":"team_members_synced","event_status":"started"},"idea_state_stage":8}
{"connection_status":"events_streaming","event":{"event_type":"team_members_synced","event_status":"completed"},"idea_state_stage":8}
{"connection_status":"events_streaming","event":{"event_type":"project_created","event_status":"started"},"idea_state_stage":8}
{"connection_status":"events_streaming","event":{"event_type":"project_created","event_status":"completed"},"idea_state_stage":8}
{"connection_status":"events_streaming","event":{"event_type":"sources_updated","event_status":"started"},"idea_state_stage":8}
{"connection_status":"events_streaming","event":{"event_type":"sources_updated","event_status":"completed"},"idea_state_stage":8}
{"connection_status":"events_streaming","event":{"event_type":"sprint_plan_generated","event_status":"started"},"idea_state_stage":8}
{"connection_status":"events_streaming","event":{"event_type":"sprint_plan_generated","event_status":"completed"},"idea_state_stage":8}
{"connection_status":"events_streaming","event":{"event_type":"narrative_sections_started","event_status":"started"},"idea_state_stage":8}
{"connection_status":"events_streaming","event":{"event_type":"completed","event_status":"completed","project_id":"550e8400-e29b-41d4-a716-446655440000"},"idea_state_stage":8}
{"connection_status":"events_completed","idea_state_stage":8,"response_content":"All stages completed. Project created successfully."}
```

## Error Handling

If an error occurs during event streaming, you'll receive:

```json
{
  "connection_status": "error",
  "error_message": "Error description here",
  "idea_state_stage": 8
}
```

## Frontend Integration Guide

### JavaScript/TypeScript Example

```typescript
interface Event {
  event_type:
    | "team_members_synced"
    | "project_created"
    | "sources_updated"
    | "sprint_plan_generated"
    | "narrative_sections_started"
    | "completed";
  event_status: "started" | "completed";
  project_id?: string; // Included in the final "completed" event
}

interface ChatResponse {
  connection_status:
    | "started"
    | "active"
    | "events_streaming"
    | "events_completed"
    | "error"
    | "disactive";
  event?: Event;
  idea_state_stage: number;
  response_content?: string;
  error_message?: string;
}

async function streamStageCompletion(
  sessionId: string,
  userId: string,
  userMessage: string
): Promise<void> {
  const response = await fetch("/api/streaming", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      connection_status: "active",
      session_id: sessionId,
      user_id: userId,
      user_message: userMessage,
      idea_state_stage: 8,
      user_preferences: {
        user_id: userId,
      },
    }),
  });

  const reader = response.body?.getReader();
  const decoder = new TextDecoder();

  if (!reader) {
    throw new Error("Stream not available");
  }

  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();

    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");

    // Keep the last incomplete line in buffer
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (line.trim()) {
        try {
          const chatResponse: ChatResponse = JSON.parse(line);
          handleChatResponse(chatResponse);
        } catch (error) {
          console.error("Failed to parse response:", error);
        }
      }
    }
  }

  // Process remaining buffer
  if (buffer.trim()) {
    try {
      const chatResponse: ChatResponse = JSON.parse(buffer);
      handleChatResponse(chatResponse);
    } catch (error) {
      console.error("Failed to parse final response:", error);
    }
  }
}

function handleChatResponse(response: ChatResponse): void {
  if (response.connection_status === "events_streaming" && response.event) {
    const { event_type, event_status } = response.event;

    // Update UI based on event
    switch (event_type) {
      case "team_members_synced":
        if (event_status === "started") {
          updateProgress("Syncing team members...");
        } else {
          updateProgress("Team members synced ✓");
        }
        break;

      case "project_created":
        if (event_status === "started") {
          updateProgress("Creating project...");
        } else {
          updateProgress("Project created ✓");
        }
        break;

      case "sources_updated":
        if (event_status === "started") {
          updateProgress("Updating documents...");
        } else {
          updateProgress("Documents updated ✓");
        }
        break;

      case "sprint_plan_generated":
        if (event_status === "started") {
          updateProgress("Generating sprint plan...");
        } else {
          updateProgress("Sprint plan generated ✓");
        }
        break;

      case "narrative_sections_started":
        updateProgress(
          "Starting narrative sections generation (running in background)..."
        );
        break;

      case "completed":
        updateProgress("Stage completion finished ✓");
        // Extract project_id from the event for navigation
        if (response.event?.project_id) {
          const projectId = response.event.project_id;
          // Navigate to project or store for later use
          console.log("Project created with ID:", projectId);
        }
        break;
    }
  } else if (response.connection_status === "events_completed") {
    showSuccessMessage(
      response.response_content || "All stages completed successfully!"
    );
    // Navigate to project view or show success screen
  } else if (response.connection_status === "error") {
    showErrorMessage(response.error_message || "An error occurred");
  }
}

function updateProgress(message: string): void {
  // Update your progress UI here
  console.log("Progress:", message);
  // Example: setProgressMessage(message);
}

function showSuccessMessage(message: string): void {
  // Show success notification
  console.log("Success:", message);
  // Example: toast.success(message);
}

function showErrorMessage(message: string): void {
  // Show error notification
  console.error("Error:", message);
  // Example: toast.error(message);
}
```

### React Example with Hooks

```typescript
import { useState, useCallback } from "react";

interface EventProgress {
  team_members_synced: "idle" | "started" | "completed";
  project_created: "idle" | "started" | "completed";
  sources_updated: "idle" | "started" | "completed";
  sprint_plan_generated: "idle" | "started" | "completed";
  narrative_sections_started: "idle" | "started";
  completed: "idle" | "completed";
}

export function useStageCompletion() {
  const [progress, setProgress] = useState<EventProgress>({
    project_created: "idle",
    sources_updated: "idle",
    team_members_synced: "idle",
    sprint_plan_generated: "idle",
    narrative_sections_started: "idle",
    completed: "idle",
  });
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const startCompletion = useCallback(
    async (sessionId: string, userId: string, userMessage: string) => {
      setIsStreaming(true);
      setError(null);
      setProgress({
        team_members_synced: "idle",
        project_created: "idle",
        sources_updated: "idle",
        sprint_plan_generated: "idle",
        narrative_sections_started: "idle",
        completed: "idle",
      });

      try {
        const response = await fetch("/api/streaming", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            connection_status: "active",
            session_id: sessionId,
            user_id: userId,
            user_message: userMessage,
            idea_state_stage: 8,
          }),
        });

        const reader = response.body?.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        if (!reader) throw new Error("Stream not available");

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";

          for (const line of lines) {
            if (line.trim()) {
              const chatResponse = JSON.parse(line);

              if (
                chatResponse.connection_status === "events_streaming" &&
                chatResponse.event
              ) {
                const { event_type, event_status, project_id } =
                  chatResponse.event;

                setProgress((prev) => ({
                  ...prev,
                  [event_type]:
                    event_status === "started" ? "started" : "completed",
                }));

                // Extract project_id from completed event
                if (
                  event_type === "completed" &&
                  event_status === "completed" &&
                  project_id
                ) {
                  // Store project_id for navigation or further use
                  console.log("Project created with ID:", project_id);
                  // Example: navigateToProject(project_id);
                }
              } else if (
                chatResponse.connection_status === "events_completed"
              ) {
                setIsStreaming(false);
              } else if (chatResponse.connection_status === "error") {
                setError(chatResponse.error_message || "Unknown error");
                setIsStreaming(false);
              }
            }
          }
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Streaming failed");
        setIsStreaming(false);
      }
    },
    []
  );

  return { progress, isStreaming, error, startCompletion };
}
```

## Important Notes

1. **NDJSON Format**: Each line is a complete JSON object. Always split by `\n` and parse each line separately.

2. **Buffer Management**: Incomplete JSON objects may be split across chunks. Always maintain a buffer for incomplete lines.

3. **Narrative Sections**: The `narrative_sections_started` event only sends a "started" status. The generation runs in the background and does not block the completion flow.

4. **Connection Status**:

   - `events_streaming`: Events are being streamed
   - `events_completed`: All events have been sent
   - `error`: An error occurred

5. **Error Handling**: Always handle errors gracefully. The stream may end with an error response.

6. **Stage Number**: The `idea_state_stage` will be `8` for all event responses, as events occur after stage 8 completion.

## Testing

You can test the event streaming using curl:

```bash
curl -X POST http://localhost:8000/api/streaming \
  -H "Content-Type: application/json" \
  -d '{
    "connection_status": "active",
    "session_id": "test_session",
    "user_id": "test_user",
    "user_message": "Complete stage 8",
    "idea_state_stage": 8
  }' \
  --no-buffer
```

The `--no-buffer` flag ensures you see events as they stream.
