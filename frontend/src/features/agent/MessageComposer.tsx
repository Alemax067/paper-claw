import { FormEvent, useState } from 'react';

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

  return (
    <form className="composer form-grid" onSubmit={submit}>
      <label>
        Command message {activePaperId && <span>· active paper #{activePaperId}</span>}
        <textarea
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          placeholder="Ask the agent to find, acquire, parse, compare, or review papers..."
          disabled={disabled || submitting}
        />
      </label>
      <div className="button-row">
        {promptChips.map((chip) => (
          <button className="chip-button" type="button" key={chip} onClick={() => setMessage(chip)}>
            {chip}
          </button>
        ))}
      </div>
      <div className="button-row">
        <button className="primary-button" type="submit" disabled={disabled || submitting || !message.trim()}>
          {submitting ? 'Dispatching...' : 'Dispatch agent'}
        </button>
      </div>
    </form>
  );
}
