import { FormEvent, KeyboardEvent, useState } from 'react';

interface MessageComposerProps {
  disabled?: boolean;
  activePaperId: number | null;
  onSubmit: (message: string) => Promise<void>;
}

const promptChips = [
  'Find the target paper and prepare a concise research brief.',
  'Acquire the PDF or source if available, then explain the method.',
  'Compare this paper against related retrieval and agent work.',
];

export function MessageComposer({ disabled = false, activePaperId, onSubmit }: MessageComposerProps) {
  const [message, setMessage] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const submit = async (event?: FormEvent) => {
    event?.preventDefault();
    const trimmed = message.trim();
    if (!trimmed) {
      return;
    }
    setSubmitting(true);
    try {
      await onSubmit(trimmed);
      setMessage('');
    } finally {
      setSubmitting(false);
    }
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      void submit();
    }
  };

  return (
    <form className="composer chat-composer" onSubmit={submit}>
      <div className="chat-composer__box">
        <label>
          <span className="chat-composer__label">
            Ask Paper Claw
            {activePaperId && <span className="active-context-chip">paper #{activePaperId}</span>}
          </span>
          <textarea
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Ask the agent to find, acquire, parse, compare, or review papers..."
            disabled={disabled || submitting}
            rows={3}
          />
        </label>
        <div className="chat-composer__footer">
          <div className="button-row">
            {promptChips.map((chip) => (
              <button className="chip-button" type="button" key={chip} onClick={() => setMessage(chip)} disabled={disabled || submitting}>
                {chip}
              </button>
            ))}
          </div>
          <button className="primary-button" type="submit" disabled={disabled || submitting || !message.trim()}>
            {submitting ? 'Streaming...' : 'Send'}
          </button>
        </div>
      </div>
    </form>
  );
}
