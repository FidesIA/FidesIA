/**
 * API wrapper for FidesIA
 * Handles JWT auth, fetch, and SSE streaming.
 */
const API = {
    getToken() { return localStorage.getItem('fidesia_token'); },
    setToken(t) { localStorage.setItem('fidesia_token', t); },
    clearToken() { localStorage.removeItem('fidesia_token'); },

    getUserId() { return localStorage.getItem('fidesia_user_id'); },
    setUserId(id) { localStorage.setItem('fidesia_user_id', id); },

    getDisplayName() { return localStorage.getItem('fidesia_display_name') || ''; },
    setDisplayName(n) { localStorage.setItem('fidesia_display_name', n); },

    getSessionId() {
        let sid = sessionStorage.getItem('fidesia_session');
        if (!sid) {
            sid = crypto.randomUUID();
            sessionStorage.setItem('fidesia_session', sid);
        }
        return sid;
    },

    headers(json = true) {
        const h = {};
        const token = this.getToken();
        if (token) h['Authorization'] = `Bearer ${token}`;
        if (json) h['Content-Type'] = 'application/json';
        return h;
    },

    async request(method, path, body = null) {
        const opts = { method, headers: this.headers(!!body) };
        if (body) opts.body = JSON.stringify(body);
        const res = await fetch(path, opts);

        if (res.status === 401) {
            this.clearToken();
            if (typeof App !== 'undefined') App.onSessionExpired();
            throw new Error('Session expirée');
        }
        if (!res.ok) {
            const data = await res.json().catch(() => ({}));
            throw new Error(data.detail || data.message || `Erreur ${res.status}`);
        }
        return res.json();
    },

    get(path) { return this.request('GET', path); },
    post(path, body) { return this.request('POST', path, body); },
    del(path) { return this.request('DELETE', path); },

    /**
     * Stream SSE response from POST /ask/stream
     */
    streamQuestion(payload, { onChunk, onSources, onDone, onError }) {
        const controller = new AbortController();

        fetch('/ask/stream', {
            method: 'POST',
            headers: this.headers(true),
            body: JSON.stringify(payload),
            signal: controller.signal,
        }).then(async (res) => {
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                onError(err.detail || `Erreur ${res.status}`);
                return;
            }

            const reader = res.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            let gotDone = false;

            const processLine = (line) => {
                if (!line.startsWith('data: ')) return;
                try {
                    const event = JSON.parse(line.slice(6));
                    if (event.type === 'chunk' && event.content) onChunk(event.content);
                    else if (event.type === 'sources') onSources(event.sources_with_scores || []);
                    else if (event.type === 'error') onError(event.content || 'Erreur inconnue');
                    else if (event.type === 'done') { gotDone = true; onDone(); }
                } catch (_) { /* skip malformed SSE */ }
            };

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop();

                for (const line of lines) processLine(line);
            }

            // Process remaining buffer
            if (buffer) processLine(buffer);
            if (!gotDone) onDone();
        }).catch((err) => {
            if (err.name !== 'AbortError') onError(err.message);
        });

        return controller;
    },

    // Auth
    register(email, password, display_name) {
        return this.post('/auth/register', { email, password, display_name });
    },
    login(email, password) {
        return this.post('/auth/login', { email, password });
    },
    logout() {
        return this.post('/auth/logout', {}).catch((e) => {
            console.warn('Logout request failed:', e.message);
        });
    },
    checkSession() { return this.get('/auth/check'); },

    // Conversations
    listConversations() { return this.get('/conversations'); },
    getConversation(id) { return this.get(`/conversations/${encodeURIComponent(id)}/messages`); },
    saveExchange(data) { return this.post('/conversations/exchange', data); },
    deleteConversation(id) { return this.del(`/conversations/${encodeURIComponent(id)}`); },
    deleteExchange(id) { return this.del(`/exchanges/${encodeURIComponent(id)}`); },

    // Password reset
    forgotPassword(email) { return this.post('/auth/forgot-password', { email }); },
    resetPassword(token, password) { return this.post('/auth/reset-password', { token, password }); },

    // Rating
    rate(data) { return this.post('/rate', data); },

    // Corpus
    corpus() { return this.get('/corpus'); },

    // Health
    health() { return this.get('/health'); },
};
