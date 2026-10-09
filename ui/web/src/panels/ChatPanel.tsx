import { useEffect, useRef, useState } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent } from 'react';

import { Markdown } from '../components/Markdown';
import { SendIcon } from '../components/icons';
import { SEED } from '../lib/api';
import { useCore } from '../state/core';
import type { ChatMessage } from '../lib/types';

function Message({ message }: { message: ChatMessage }) {
  const isUser = message.role === 'user';
  return (
    <article className={`msg ${isUser ? 'msg--user' : 'msg--assistant'}`}>
      <div className="msg__avatar">{isUser ? 'YOU' : 'NV'}</div>
      <div className="msg__body">
        <div className="msg__meta">
          <span>{isUser ? 'You' : 'Nova'}</span>
          {message.model ? <span className="pill">{message.model}</span> : null}
          {message.error ? <span className="pill pill--bad">error</span> : null}
          {message.streaming ? <span className="pill pill--ok">streaming</span> : null}
        </div>
        <div className="msg__text">
          {message.error ? (
            <span>{message.text}</span>
          ) : (
            <>
              <Markdown>{message.text}</Markdown>
              {message.streaming ? <span className="caret" /> : null}
            </>
          )}
        </div>
      </div>
    </article>
  );
}

export function ChatPanel() {
  const { messages, sendMessage, clearChat, connection } = useCore();
  const [draft, setDraft] = useState('');
  const listRef = useRef<HTMLDivElement | null>(null);
  const seeded = useRef(false);

  // Optional demo hook: send a message as soon as the socket is open.
  useEffect(() => {
    if (seeded.current || !SEED) return;
    if (connection === 'open' && messages.length === 0) {
      seeded.current = true;
      sendMessage(SEED);
    }
  }, [connection, messages.length, sendMessage]);

  useEffect(() => {
    const element = listRef.current;
    if (element) {
      element.scrollTop = element.scrollHeight;
    }
  }, [messages]);

  const submit = () => {
    if (!draft.trim()) return;
    sendMessage(draft);
    setDraft('');
  };

  const onKeyDown = (event: ReactKeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  };

  return (
    <section className="panel">
      <header className="panel__head">
        <h1 className="panel__title">Chat</h1>
        <span className="panel__sub">mock backend · streaming, markdown and code blocks</span>
        <div className="titlebar__spacer" />
        <button type="button" className="btn btn--ghost" onClick={clearChat} disabled={!messages.length}>
          Clear
        </button>
      </header>

      <div className="chat">
        <div className="chat__list" ref={listRef}>
          {messages.length === 0 ? (
            <div className="placeholder">
              <div className="placeholder__inner">
                <h2 className="placeholder__title">No messages yet</h2>
                <p className="placeholder__text">
                  Try “show me a python function” or “summarise the project status” — the
                  Phase 2 mock backend answers with markdown and code.
                </p>
              </div>
            </div>
          ) : (
            messages.map((message) => <Message key={message.id} message={message} />)
          )}
        </div>

        <div className="chat__composer">
          <textarea
            className="chat__input"
            rows={1}
            value={draft}
            placeholder={connection === 'open' ? 'Ask NOVA anything…' : 'Waiting for the NOVA core…'}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={onKeyDown}
            aria-label="Message"
          />
          <button
            type="button"
            className="btn btn--primary"
            onClick={submit}
            disabled={!draft.trim()}
          >
            <SendIcon className="nav__icon" />
            Send
          </button>
        </div>
        <div className="chat__hint">Enter to send · Shift+Enter for a new line</div>
      </div>
    </section>
  );
}
