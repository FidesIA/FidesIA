/**
 * Chat — Messages, streaming, sources, rating
 * Throttled markdown rendering (requestAnimationFrame), event delegation for ratings.
 */
const Chat = {
    messages: [],
    conversationId: null,
    streamController: null,
    isStreaming: false,
    _streamingMsg: null,
    _streamCtx: null,

    init() {
        const form = document.getElementById('chat-form');
        const input = document.getElementById('chat-input');

        form.addEventListener('submit', (e) => {
            e.preventDefault();
            this.send();
        });

        // Auto-resize textarea
        const _resizeInput = () => {
            input.style.height = 'auto';
            input.style.height = Math.min(input.scrollHeight, 150) + 'px';
        };
        input.addEventListener('input', _resizeInput);

        // Recalc on orientation change / keyboard show
        window.addEventListener('orientationchange', () => setTimeout(_resizeInput, 150));
        input.addEventListener('focus', () => {
            setTimeout(() => input.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 300);
        });

        // Enter to send, Shift+Enter for newline
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.send();
            }
        });

        // Example questions (event delegation)
        document.getElementById('welcome-examples').addEventListener('click', (e) => {
            const btn = e.target.closest('.example-btn');
            if (btn) {
                API.track('click_example', { label: btn.textContent });
                input.value = btn.dataset.q;
                this.send();
            }
        });

        // Event delegation for ratings (pointer events work on both mouse + touch)
        document.getElementById('messages').addEventListener('pointerenter', (e) => {
            const star = e.target.closest('.rating-star');
            if (!star) return;
            const container = star.closest('.rating-container');
            if (!container) return;
            const val = parseInt(star.dataset.value);
            container.querySelectorAll('.rating-star').forEach(s => {
                s.classList.toggle('hovered', parseInt(s.dataset.value) <= val);
            });
        }, true);

        document.getElementById('messages').addEventListener('pointerleave', (e) => {
            const star = e.target.closest('.rating-star');
            if (!star) return;
            const container = star.closest('.rating-container');
            if (!container) return;
            container.querySelectorAll('.rating-star').forEach(s => s.classList.remove('hovered'));
        }, true);

        document.getElementById('messages').addEventListener('click', (e) => {
            // Rating star click
            const star = e.target.closest('.rating-star');
            if (star) {
                const container = star.closest('.rating-container');
                if (!container) return;
                const exchangeId = container.dataset.exchangeId;
                if (!exchangeId) return;
                const val = parseInt(star.dataset.value);
                container.dataset.rating = val;
                container.querySelectorAll('.rating-star').forEach(s => {
                    s.classList.toggle('active', parseInt(s.dataset.value) <= val);
                });
                API.rate({
                    exchange_id: parseInt(exchangeId),
                    rating: val,
                    session_id: API.getSessionId(),
                }).catch(err => console.warn('Rating failed:', err));
                return;
            }

            // Message action buttons (share, copy, delete)
            const actionBtn = e.target.closest('.btn-mini-action');
            if (actionBtn) {
                const action = actionBtn.dataset.action;
                const msgEl = actionBtn.closest('.message');
                if (!msgEl) return;

                if (action === 'share') {
                    const text = msgEl.dataset.text || '';
                    if (navigator.share) {
                        navigator.share({ title: 'FidesIA', text }).catch(() => {});
                    } else {
                        navigator.clipboard.writeText(text).catch(() => {});
                    }
                } else if (action === 'copy') {
                    const text = msgEl.dataset.text || '';
                    navigator.clipboard.writeText(text).then(() => {
                        const icon = actionBtn.querySelector('svg');
                        const original = actionBtn.innerHTML;
                        actionBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>';
                        setTimeout(() => { actionBtn.innerHTML = original; }, 2000);
                    }).catch(() => {});
                } else if (action === 'delete') {
                    let pairEl = null;
                    let targetMsg = msgEl;

                    if (msgEl.classList.contains('message-user')) {
                        // Deleting user → pair with the next assistant msg
                        const next = msgEl.nextElementSibling;
                        if (next && next.classList.contains('message-assistant')) {
                            pairEl = next;
                            targetMsg = next;
                        }
                    } else {
                        // Deleting assistant → pair with preceding user msg
                        const prev = msgEl.previousElementSibling;
                        if (prev && prev.classList.contains('message-user')) pairEl = prev;
                    }

                    // Find exchange_id: rating container OR data attribute on assistant msg
                    const ratingEl = targetMsg.querySelector('.rating-container');
                    const exchangeId = (ratingEl && ratingEl.dataset.exchangeId)
                        || targetMsg.dataset.exchangeId || null;

                    if (pairEl) pairEl.remove();
                    msgEl.remove();

                    if (exchangeId) {
                        API.deleteExchange(parseInt(exchangeId)).catch(err => {
                            console.warn('Delete exchange failed:', err);
                        });
                    }
                }
                return;
            }

            // Source name click → open PDF
            const sourceName = e.target.closest('.source-name');
            if (sourceName && sourceName.dataset.pdf) {
                Corpus.openPdf(sourceName.dataset.pdf);
                return;
            }

            // Sources toggle
            const toggle = e.target.closest('.sources-toggle');
            if (toggle) {
                const list = toggle.nextElementSibling;
                if (list) {
                    list.hidden = !list.hidden;
                    toggle.classList.toggle('open');
                }
            }
        });
    },

    send() {
        const input = document.getElementById('chat-input');
        const question = input.value.trim();
        if (!question || this.isStreaming) return;

        // Generate conversation ID if new (crypto-random)
        if (!this.conversationId) {
            this.conversationId = crypto.randomUUID();
        }

        // Hide welcome, show messages
        document.getElementById('welcome').hidden = true;
        document.getElementById('messages').hidden = false;

        // Add user message
        this.messages.push({ role: 'user', content: question });
        this._renderUserMessage(question);

        // Clear input
        input.value = '';
        input.style.height = 'auto';

        // Track question event
        API.track(App.state.authenticated ? 'question_auth' : 'question_guest');

        // Start streaming
        this._streamResponse(question);
    },

    _streamResponse(question) {
        this.isStreaming = true;
        const startTime = Date.now();

        const chatHistory = this.messages.slice(0, -1).map(m => ({
            role: m.role,
            content: m.content,
        }));

        const payload = {
            question,
            conversation_id: this.conversationId,
            session_id: API.getSessionId(),
            chat_history: chatHistory.length > 0 ? chatHistory : null,
            age_group: Profile.ageGroup,
            knowledge_level: Profile.knowledgeLevel,
            response_length: Profile.responseLength,
        };

        const msgEl = this._createAssistantMessage();
        this._streamingMsg = msgEl;
        const contentEl = msgEl.querySelector('.message-content');
        const ctx = { question, startTime, response: '', sources: [] };
        this._streamCtx = ctx;
        let renderScheduled = false;

        this._showStopButton();

        this.streamController = API.streamQuestion(payload, {
            onChunk: (text) => {
                if (!this.isStreaming) return;
                ctx.response += text;
                if (!renderScheduled) {
                    renderScheduled = true;
                    requestAnimationFrame(() => {
                        if (!this.isStreaming) { renderScheduled = false; return; }
                        contentEl.innerHTML = DOMPurify.sanitize(marked.parse(ctx.response));
                        this._scrollToBottom();
                        renderScheduled = false;
                    });
                }
            },
            onSources: (s) => {
                if (!this.isStreaming) return;
                ctx.sources = s;
            },
            onDone: () => {
                if (!this.isStreaming) return;
                this.isStreaming = false;
                this.streamController = null;
                this._streamingMsg = null;
                this._streamCtx = null;
                const elapsed = Date.now() - ctx.startTime;

                this._hideStopButton();

                contentEl.innerHTML = DOMPurify.sanitize(marked.parse(ctx.response));
                msgEl.dataset.text = ctx.response;

                msgEl.appendChild(this._createMessageActions());

                if (ctx.sources.length > 0) {
                    msgEl.appendChild(this._createSourcesEl(ctx.sources));
                }

                const ratingEl = this._createRatingEl(null);
                msgEl.appendChild(ratingEl);

                this.messages.push({ role: 'assistant', content: ctx.response, sources: ctx.sources });
                Donation.onExchange();
                this._saveExchange(ctx.question, ctx.response, ctx.sources, elapsed, msgEl, ratingEl);

                this._scrollToBottom(true);
                document.getElementById('chat-input').focus();
            },
            onError: (err) => {
                if (!this.isStreaming) return;
                this.isStreaming = false;
                this.streamController = null;
                this._streamingMsg = null;
                const errCtx = this._streamCtx;
                this._streamCtx = null;
                this._hideStopButton();

                if (errCtx && errCtx.response) {
                    const finalText = errCtx.response + '\n\n*[Réponse interrompue — erreur réseau]*';
                    contentEl.innerHTML = DOMPurify.sanitize(marked.parse(finalText));
                    msgEl.dataset.text = finalText;
                    this.messages.push({ role: 'assistant', content: finalText, sources: errCtx.sources });
                    this._saveExchange(errCtx.question, finalText, errCtx.sources, Date.now() - errCtx.startTime, msgEl, null);
                } else {
                    contentEl.innerHTML = `<span style="color:var(--accent)">Erreur : ${DOMPurify.sanitize(err)}</span>`;
                }

                const actions = this._createMessageActions();
                actions.style.display = 'flex';
                msgEl.appendChild(actions);
                this._scrollToBottom(true);
            },
        });
    },

    async _saveExchange(question, response, sources, elapsed, msgEl, ratingEl) {
        try {
            const data = await API.saveExchange({
                conversation_id: this.conversationId,
                session_id: API.getSessionId(),
                question,
                response,
                sources,
                age_group: Profile.ageGroup,
                knowledge_level: Profile.knowledgeLevel,
                response_time_ms: elapsed,
            });
            if (data.exchange_id) {
                if (ratingEl) ratingEl.dataset.exchangeId = data.exchange_id;
                if (msgEl) msgEl.dataset.exchangeId = data.exchange_id;
            }
            App.loadConversations();
        } catch (e) {
            console.warn('Save exchange failed:', e);
        }
    },

    cancelStream() {
        if (this.streamController) {
            this.isStreaming = false;
            this.streamController.abort();
            this.streamController = null;
            this._hideStopButton();

            const msgEl = this._streamingMsg;
            this._streamingMsg = null;
            const ctx = this._streamCtx;
            this._streamCtx = null;

            if (msgEl) {
                const contentEl = msgEl.querySelector('.message-content');
                const partialText = ctx ? ctx.response : '';

                if (contentEl) {
                    if (partialText) {
                        const finalText = partialText + '\n\n*[Réponse interrompue par l\'utilisateur]*';
                        contentEl.innerHTML = DOMPurify.sanitize(marked.parse(finalText));
                        msgEl.dataset.text = finalText;

                        this.messages.push({ role: 'assistant', content: finalText, sources: ctx.sources });
                        this._saveExchange(ctx.question, finalText, ctx.sources, Date.now() - ctx.startTime, msgEl, null);
                    } else {
                        contentEl.innerHTML = '<em style="color:var(--text-muted)">Génération interrompue</em>';
                        msgEl.dataset.text = '';
                    }
                }

                const actions = this._createMessageActions();
                actions.style.display = 'flex';
                msgEl.appendChild(actions);
            }
        }
    },

    newChat() {
        this.cancelStream();
        this.messages = [];
        this.conversationId = null;
        document.getElementById('messages').innerHTML = '';
        document.getElementById('messages').hidden = true;
        document.getElementById('welcome').hidden = false;
        document.getElementById('chat-input').focus();

        document.querySelectorAll('.conv-item.active').forEach(el => el.classList.remove('active'));
    },

    async loadConversation(convId) {
        try {
            const msgs = await API.getConversation(convId);
            this.messages = msgs;
            this.conversationId = convId;

            document.getElementById('welcome').hidden = true;
            const container = document.getElementById('messages');
            container.innerHTML = '';
            container.hidden = false;

            for (const msg of msgs) {
                if (msg.role === 'user') {
                    this._renderUserMessage(msg.content);
                } else {
                    const el = this._createAssistantMessage();
                    el.querySelector('.message-content').innerHTML = DOMPurify.sanitize(marked.parse(msg.content));
                    el.dataset.text = msg.content;
                    if (msg.exchange_id) el.dataset.exchangeId = msg.exchange_id;
                    el.appendChild(this._createMessageActions());
                    if (msg.sources_with_scores && msg.sources_with_scores.length > 0) {
                        el.appendChild(this._createSourcesEl(msg.sources_with_scores));
                    }
                    const ratingEl = this._createRatingEl(msg.rating);
                    if (msg.exchange_id) ratingEl.dataset.exchangeId = msg.exchange_id;
                    el.appendChild(ratingEl);
                }
            }

            this._scrollToBottom(true);

            document.querySelectorAll('.conv-item').forEach(el => {
                el.classList.toggle('active', el.dataset.id === convId);
            });
        } catch (e) {
            console.error('Load conversation failed:', e);
        }
    },

    // === DOM Helpers ===

    _renderUserMessage(content) {
        const container = document.getElementById('messages');
        const div = document.createElement('div');
        div.className = 'message message-user';
        div.dataset.text = content;

        const bubble = document.createElement('div');
        bubble.className = 'message-content';
        bubble.textContent = content;

        div.appendChild(bubble);
        div.appendChild(this._createMessageActions());
        container.appendChild(div);
        this._scrollToBottom(true);
    },

    _createAssistantMessage() {
        const container = document.getElementById('messages');
        const div = document.createElement('div');
        div.className = 'message message-assistant';
        div.innerHTML = '<div class="message-content"><div class="loading-dots"><span></span><span></span><span></span></div></div>';
        container.appendChild(div);
        return div;
    },

    _showStopButton() {
        const sendBtn = document.getElementById('send-btn');
        sendBtn.hidden = true;
        let stopBtn = document.getElementById('stop-btn');
        if (!stopBtn) {
            stopBtn = document.createElement('button');
            stopBtn.type = 'button';
            stopBtn.id = 'stop-btn';
            stopBtn.className = 'btn stop-btn-input';
            stopBtn.title = 'Arrêter';
            stopBtn.setAttribute('aria-label', 'Arrêter la génération');
            stopBtn.innerHTML = '<svg viewBox="0 0 24 24"><rect x="6" y="6" width="12" height="12" rx="1" fill="white"/></svg>';
            stopBtn.addEventListener('click', () => this.cancelStream());
            sendBtn.parentNode.insertBefore(stopBtn, sendBtn.nextSibling);
        }
        stopBtn.hidden = false;
    },

    _hideStopButton() {
        const sendBtn = document.getElementById('send-btn');
        const stopBtn = document.getElementById('stop-btn');
        if (stopBtn) stopBtn.hidden = true;
        sendBtn.hidden = false;
    },

    _createMessageActions() {
        const actions = document.createElement('div');
        actions.className = 'message-actions';

        actions.innerHTML = `
            <button class="btn-mini-action" data-action="share" title="Partager" aria-label="Partager">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 12v8a2 2 0 002 2h12a2 2 0 002-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/></svg>
            </button>
            <button class="btn-mini-action" data-action="copy" title="Copier" aria-label="Copier">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>
            </button>
            <button class="btn-mini-action btn-mini-danger" data-action="delete" title="Supprimer" aria-label="Supprimer">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>
            </button>`;

        return actions;
    },

    _createSourcesEl(sources) {
        const wrapper = document.createElement('div');
        wrapper.className = 'sources-container';

        const toggle = document.createElement('button');
        toggle.className = 'sources-toggle';
        toggle.innerHTML = `<span class="arrow">&#9654;</span> ${sources.length} source${sources.length > 1 ? 's' : ''}`;

        const list = document.createElement('div');
        list.className = 'sources-list';
        list.hidden = true;

        const corpusData = Corpus.data || [];

        for (const src of sources) {
            const item = document.createElement('div');
            item.className = 'source-item';

            const name = src.file_name || src.relative_path || 'Document';
            const score = src.score ? `${Math.round(src.score * 100)}%` : '';
            const pdfFile = src.relative_path || name;

            // Find vatican.va link
            const corpusMatch = corpusData.find(c => c.fichier === name);
            let vatLinkHtml = '';
            if (corpusMatch && corpusMatch.url) {
                try {
                    const parsed = new URL(corpusMatch.url);
                    if (parsed.protocol === 'http:' || parsed.protocol === 'https:') {
                        vatLinkHtml = `<a class="source-vatican" href="${DOMPurify.sanitize(corpusMatch.url)}" target="_blank" rel="noopener">vatican.va</a>`;
                    }
                } catch (_) {}
            }

            item.innerHTML = `<span class="source-name" data-pdf="${DOMPurify.sanitize(pdfFile)}">${DOMPurify.sanitize(name)}</span>${vatLinkHtml}<span class="source-score">${score}</span>`;
            list.appendChild(item);
        }

        wrapper.appendChild(toggle);
        wrapper.appendChild(list);
        return wrapper;
    },

    _createRatingEl(currentRating) {
        const container = document.createElement('div');
        container.className = 'rating-container';
        container.dataset.rating = currentRating || 0;

        let html = '';
        for (let i = 1; i <= 5; i++) {
            const active = currentRating && i <= currentRating ? ' active' : '';
            html += `<button class="rating-star${active}" data-value="${i}" aria-label="${i} étoile${i > 1 ? 's' : ''}">\u2605</button>`;
        }
        container.innerHTML = html;
        return container;
    },

    _scrollToBottom(force) {
        const area = document.getElementById('chat-area');
        // Don't force scroll if user has scrolled up to read earlier messages
        if (!force) {
            const distFromBottom = area.scrollHeight - area.scrollTop - area.clientHeight;
            if (distFromBottom > 150) return;
        }
        requestAnimationFrame(() => {
            area.scrollTop = area.scrollHeight;
        });
    },
};
