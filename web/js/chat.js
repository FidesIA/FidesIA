/**
 * Chat — Messages, streaming, sources, rating
 */
const Chat = {
    messages: [],
    conversationId: null,
    streamController: null,
    isStreaming: false,

    init() {
        const form = document.getElementById('chat-form');
        const input = document.getElementById('chat-input');

        form.addEventListener('submit', (e) => {
            e.preventDefault();
            this.send();
        });

        // Auto-resize textarea
        input.addEventListener('input', () => {
            input.style.height = 'auto';
            input.style.height = Math.min(input.scrollHeight, 150) + 'px';
        });

        // Enter to send, Shift+Enter for newline
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.send();
            }
        });

        // Example questions (event delegation for dynamically created buttons)
        document.getElementById('welcome-examples').addEventListener('click', (e) => {
            const btn = e.target.closest('.example-btn');
            if (btn) {
                input.value = btn.dataset.q;
                this.send();
            }
        });
    },

    send() {
        const input = document.getElementById('chat-input');
        const question = input.value.trim();
        if (!question || this.isStreaming) return;

        // Generate conversation ID if new
        if (!this.conversationId) {
            this.conversationId = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
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

        // Start streaming
        this._streamResponse(question);
    },

    _streamResponse(question) {
        this.isStreaming = true;
        const startTime = Date.now();

        // Build chat history for context
        const chatHistory = this.messages.slice(0, -1).map(m => ({
            role: m.role,
            content: m.content
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

        // Create assistant message placeholder
        const msgEl = this._createAssistantMessage();
        const contentEl = msgEl.querySelector('.message-content');
        let fullResponse = '';
        let sources = [];

        // Replace send button with stop button in input area
        this._showStopButton();

        this.streamController = API.streamQuestion(payload, {
            onChunk: (text) => {
                fullResponse += text;
                contentEl.innerHTML = DOMPurify.sanitize(marked.parse(fullResponse));
                this._scrollToBottom();
            },
            onSources: (s) => {
                sources = s;
            },
            onDone: () => {
                this.isStreaming = false;
                this.streamController = null;
                const elapsed = Date.now() - startTime;

                // Restore send button
                this._hideStopButton();

                // Final render (no cursor)
                contentEl.innerHTML = DOMPurify.sanitize(marked.parse(fullResponse));

                // Add actions (share, copy, delete)
                msgEl.appendChild(this._createMessageActions(fullResponse, msgEl));

                // Add sources
                if (sources.length > 0) {
                    msgEl.appendChild(this._createSourcesEl(sources));
                }

                // Add rating
                const ratingEl = this._createRatingEl(null);
                msgEl.appendChild(ratingEl);

                // Save to messages array
                this.messages.push({
                    role: 'assistant',
                    content: fullResponse,
                    sources,
                });

                // Track for donation popup
                Donation.onExchange();

                // Save exchange to server
                this._saveExchange(question, fullResponse, sources, elapsed, ratingEl);

                this._scrollToBottom();
                document.getElementById('chat-input').focus();
            },
            onError: (err) => {
                this.isStreaming = false;
                this.streamController = null;
                this._hideStopButton();
                contentEl.innerHTML = `<span style="color:var(--accent)">Erreur : ${DOMPurify.sanitize(err)}</span>`;
                this._scrollToBottom();
            }
        });
    },

    async _saveExchange(question, response, sources, elapsed, ratingEl) {
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
                ratingEl.dataset.exchangeId = data.exchange_id;
            }
            // Refresh sidebar conversations
            App.loadConversations();
        } catch (e) {
            console.warn('Save exchange failed:', e);
        }
    },

    cancelStream() {
        if (this.streamController) {
            this.streamController.abort();
            this.streamController = null;
            this.isStreaming = false;
            this._hideStopButton();
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

        // Deselect sidebar
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
                    el.appendChild(this._createMessageActions(msg.content, el));
                    if (msg.sources_with_scores && msg.sources_with_scores.length > 0) {
                        el.appendChild(this._createSourcesEl(msg.sources_with_scores));
                    }
                    const ratingEl = this._createRatingEl(msg.rating);
                    if (msg.exchange_id) ratingEl.dataset.exchangeId = msg.exchange_id;
                    el.appendChild(ratingEl);
                }
            }

            this._scrollToBottom();

            // Highlight in sidebar
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

        const bubble = document.createElement('div');
        bubble.className = 'message-content';
        bubble.textContent = content;

        div.appendChild(bubble);
        div.appendChild(this._createMessageActions(content, div));
        container.appendChild(div);
        this._scrollToBottom();
    },

    _createAssistantMessage() {
        const container = document.getElementById('messages');
        const div = document.createElement('div');
        div.className = 'message message-assistant';
        div.innerHTML = `<div class="message-content"><div class="loading-dots"><span></span><span></span><span></span></div></div>`;
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

    _createMessageActions(text, msgEl) {
        const actions = document.createElement('div');
        actions.className = 'message-actions';

        // Share
        const shareBtn = document.createElement('button');
        shareBtn.className = 'btn-mini-action';
        shareBtn.title = 'Partager';
        shareBtn.setAttribute('aria-label', 'Partager');
        shareBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 12v8a2 2 0 002 2h12a2 2 0 002-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/></svg>';
        shareBtn.addEventListener('click', () => {
            if (navigator.share) {
                navigator.share({ title: 'FidesIA', text }).catch(() => {});
            } else {
                navigator.clipboard.writeText(text).catch(() => {});
            }
        });

        // Copy
        const copyBtn = document.createElement('button');
        copyBtn.className = 'btn-mini-action';
        copyBtn.title = 'Copier';
        copyBtn.setAttribute('aria-label', 'Copier');
        const copyIcon = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>';
        copyBtn.innerHTML = copyIcon;
        copyBtn.addEventListener('click', async () => {
            try {
                await navigator.clipboard.writeText(text);
                copyBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>';
                setTimeout(() => { copyBtn.innerHTML = copyIcon; }, 2000);
            } catch (_) {}
        });

        // Delete (DOM-only, for reshaping before export)
        const deleteBtn = document.createElement('button');
        deleteBtn.className = 'btn-mini-action btn-mini-danger';
        deleteBtn.title = 'Supprimer';
        deleteBtn.setAttribute('aria-label', 'Supprimer');
        deleteBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>';
        deleteBtn.addEventListener('click', () => {
            const el = msgEl || deleteBtn.closest('.message');
            if (el) el.remove();
        });

        actions.appendChild(shareBtn);
        actions.appendChild(copyBtn);
        actions.appendChild(deleteBtn);
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

        // Lookup vatican.va URLs from corpus data
        const corpusData = Corpus.data || [];

        for (const src of sources) {
            const item = document.createElement('div');
            item.className = 'source-item';

            const name = src.file_name || src.relative_path || 'Document';
            const score = src.score ? `${Math.round(src.score * 100)}%` : '';

            // Find vatican.va link (with URL validation)
            const corpusMatch = corpusData.find(c => c.fichier === name);
            let vatLink = null;
            if (corpusMatch && corpusMatch.url) {
                try {
                    const parsed = new URL(corpusMatch.url);
                    if (parsed.protocol === 'http:' || parsed.protocol === 'https:') {
                        vatLink = document.createElement('a');
                        vatLink.className = 'source-vatican';
                        vatLink.href = corpusMatch.url;
                        vatLink.target = '_blank';
                        vatLink.rel = 'noopener';
                        vatLink.textContent = 'vatican.va';
                    }
                } catch (_) { /* skip invalid URLs */ }
            }

            // Build PDF path for click
            const pdfFile = src.relative_path || name;

            const nameSpan = document.createElement('span');
            nameSpan.className = 'source-name';
            nameSpan.textContent = name;
            nameSpan.addEventListener('click', () => Corpus.openPdf(pdfFile));

            item.appendChild(nameSpan);
            if (vatLink) item.appendChild(vatLink);
            const scoreSpan = document.createElement('span');
            scoreSpan.className = 'source-score';
            scoreSpan.textContent = score;
            item.appendChild(scoreSpan);

            list.appendChild(item);
        }

        toggle.addEventListener('click', () => {
            list.hidden = !list.hidden;
            toggle.classList.toggle('open');
        });

        wrapper.appendChild(toggle);
        wrapper.appendChild(list);
        return wrapper;
    },

    _createRatingEl(currentRating) {
        const container = document.createElement('div');
        container.className = 'rating-container';
        container.dataset.rating = currentRating || 0;

        for (let i = 1; i <= 5; i++) {
            const star = document.createElement('button');
            star.className = 'rating-star' + (currentRating && i <= currentRating ? ' active' : '');
            star.textContent = '\u2605';
            star.dataset.value = i;
            star.setAttribute('aria-label', `${i} étoile${i > 1 ? 's' : ''}`);

            star.addEventListener('mouseenter', () => {
                container.querySelectorAll('.rating-star').forEach(s => {
                    s.classList.toggle('hovered', parseInt(s.dataset.value) <= i);
                });
            });

            star.addEventListener('mouseleave', () => {
                container.querySelectorAll('.rating-star').forEach(s => s.classList.remove('hovered'));
            });

            star.addEventListener('click', async () => {
                const exchangeId = container.dataset.exchangeId;
                if (!exchangeId) return;

                container.dataset.rating = i;
                container.querySelectorAll('.rating-star').forEach(s => {
                    s.classList.toggle('active', parseInt(s.dataset.value) <= i);
                });

                try {
                    await API.rate({ exchange_id: parseInt(exchangeId), rating: i });
                } catch (e) {
                    console.warn('Rating failed:', e);
                }
            });

            container.appendChild(star);
        }

        return container;
    },

    _scrollToBottom() {
        const area = document.getElementById('chat-area');
        requestAnimationFrame(() => {
            area.scrollTop = area.scrollHeight;
        });
    }
};
