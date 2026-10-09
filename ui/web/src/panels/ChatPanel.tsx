import { useEffect, useRef, useState } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent } from 'react';

import { Markdown } from '../components/Markdown';
import { SendIcon } from '../components/icons';
import { SEED } from '../lib/api';
import { formatArgs, formatCost, formatTokens, statusTone } from '../lib/format';
import { useCore } from '../state/core';
import type { ChatMessage } from '../lib/types';

const MODEL_LABEL: Record<string, string> = { fast: 'fast model', strong: 'strong model', local: 'local' };

function Message({ message }: { message: ChatMessage }) {
  const isUser = message.role === 'user';
  return (
    <article className={`msg ${isUser ? 'msg--user' : 'msg--assistant'}`}>
      <div className="msg__avatar">{isUser ? 'YOU' : 'NV'}</div>
      <div className="msg__body">
        <div className="msg__meta">
          <span>{isUser ? 'You' : 'Nova'}</span>
          {message.model ? <span className="pill">{message.model}</span> : null}
          {message.tier ? <span className="pill">{MODEL_LABEL[message.tier] ?? message.tier}</span> : null}
          {message.reason ? <span className="pill">{message.reason}</span> : null}
          {message.error ? (
            <span className="pill pill--bad">{message.errorKind ?? 'error'}</span>
          ) : null}
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

        {(message.tools ?? []).map((tool, index) => (
          <div className="tool" key={`${message.id}-tool-${index}`}>
            <div className="tool__head">
              <span className="tool__name">{tool.name}</span>
              <span className={`pill ${statusTone(tool.status)}`}>{tool.status}</span>
              <span className="pill">{tool.ms} ms</span>
            </div>
            <div className="tool__row">
              <span>args</span>
              <span className="tool__detail">{formatArgs(tool.args)}</span>
            </div>
            <div className="tool__row">
              <span>result</span>
              <span className="tool__detail">{tool.detail}</span>
            </div>
          </div>
        ))}

        {message.usage ? (
          <div className="msg__foot">
            <span className="pill">
              {formatTokens(message.usage.inputTokens + message.usage.outputTokens)} tokens
            </span>
            <span className="pill">{formatCost(message.usage.costUsd)}</span>
            <span className="pill">{message.usage.tier}</span>
          </div>
        ) : null}
      </div>
    </article>
  );
}

export function ChatPanel() {
  const { messages, sendMessage, cancelStream, clearChat, connection, streaming, budget, tools } =
    useCore();
  const [draft, setDraft] = useState('');
  const listRef = useRef<HTMLDivElement | null>(null);
  const seeded = useRef(false);

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
    if (!draft.trim() || streaming) return;
    sendMessage(draft);
    setDraft('');
  };

  const onKeyDown = (event: ReactKeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  };

  const blocked = budget?.allowed === false;

  return (
    <section className="panel">
      <header className="panel__head">
        <h1 className="panel__title">Chat</h1>
        <span className="panel__sub">
          {tools.length ? `${tools.length} tools` : 'no tools'}
          {blocked ? ' · budget reached' : ''}
        </span>
        <div className="titlebar__spacer" />
        <button
          type="button"
          className="btn btn--ghost"
          onClick={clearChat}
          disabled={!messages.length || streaming}
        >
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
                  Ask something, or try “what time is it?” — trivial questions are answered
                  locally without spending tokens.
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
            placeholder={
              blocked
                ? 'Budget limit reached — raise it in Settings'
                : connection === 'open'
                  ? 'Ask NOVA anything…'
                  : 'Waiting for the NOVA core…'
            }
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={onKeyDown}
            aria-label="Message"
            disabled={blocked}
          />
          {streaming ? (
            <button type="button" className="btn btn--danger" onClick={cancelStream}>
              Stop
            </button>
          ) : (
            <button
              type="button"
              className="btn btn--primary"
              onClick={submit}
              disabled={!draft.trim() || blocked}
            >
              <SendIcon className="nav__icon" />
              Send
            </button>
          )}
        </div>
        <div className="chat__hint">
          Enter to send · Shift+Enter for a new line
          {budget ? ` · today ${formatCost(budget.today_usd)}` : ''}
        </div>
      </div>
    </section>
  );
}
