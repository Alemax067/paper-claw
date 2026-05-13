import type { MessageRead } from '../../api/types';
import { EmptyState } from '../../components/EmptyState';

interface MessageTranscriptProps {
  messages: MessageRead[];
}

export function MessageTranscript({ messages }: MessageTranscriptProps) {
  if (!messages.length) {
    return (
      <EmptyState
        eyebrow="Transcript"
        title="Awaiting first instruction"
        body="Use the composer below to ask the agent to find, acquire, parse, compare, or review papers."
      />
    );
  }

  return (
    <div className="transcript">
      {messages.map((message) => (
        <article className={`message message-${message.role}`} key={message.id}>
          <div className="meta-row">
            <span>{message.role}</span>
            <span>{message.source}</span>
            <span>{new Date(message.created_at).toLocaleString()}</span>
          </div>
          {message.content_text && <p>{message.content_text}</p>}
          {message.content_json && (
            <details>
              <summary>payload</summary>
              <pre>{JSON.stringify(message.content_json, null, 2)}</pre>
            </details>
          )}
        </article>
      ))}
    </div>
  );
}
