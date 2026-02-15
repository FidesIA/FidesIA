/**
 * App — Init, state, routing
 */
const App = {
    state: {
        authenticated: false,
        userId: null,
        displayName: '',
    },

    async init() {
        // Init modules
        AuthUI.init();
        Profile.init();
        Corpus.init();
        Chat.init();

        // Header buttons
        document.getElementById('profile-btn').addEventListener('click', () => Profile.open());
        document.getElementById('corpus-btn').addEventListener('click', () => Corpus.open());
        document.getElementById('auth-btn').addEventListener('click', () => {
            if (this.state.authenticated) {
                AuthUI.logout();
            } else {
                AuthUI.open();
            }
        });
        document.getElementById('new-chat-btn').addEventListener('click', () => Chat.newChat());
        document.getElementById('sidebar-toggle').addEventListener('click', (e) => {
            e.stopPropagation();
            this.toggleSidebar();
        });

        // Close sidebar when clicking on main area (mobile)
        document.querySelector('.main').addEventListener('click', () => this.closeSidebar());

        // Check existing session
        const session = await AuthUI.checkSession();
        if (session) {
            this.state.authenticated = true;
            this.state.userId = session.user_id || API.getUserId();
            this.state.displayName = session.display_name || API.getDisplayName();
            this._showConnectedUI();
        } else {
            this._showGuestUI();
        }
    },

    onLogin(data) {
        this.state.authenticated = true;
        this.state.userId = data.user_id;
        this.state.displayName = data.display_name || '';
        this._showConnectedUI();
    },

    onLogout() {
        this.state.authenticated = false;
        this.state.userId = null;
        this.state.displayName = '';
        Chat.newChat();
        this._showGuestUI();
    },

    onSessionExpired() {
        this.state.authenticated = false;
        this._showGuestUI();
    },

    _showConnectedUI() {
        // Show sidebar
        document.getElementById('sidebar').hidden = false;
        document.getElementById('sidebar-toggle').hidden = false;

        // Update auth button to logout
        const authBtn = document.getElementById('auth-btn');
        authBtn.title = 'Se déconnecter';
        authBtn.innerHTML = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>`;

        // Hide guest banner
        document.getElementById('guest-banner').hidden = true;

        // Show user name in sidebar footer
        document.getElementById('sidebar-username').textContent = this.state.displayName || 'Connecté';

        // Load conversations
        this.loadConversations();
    },

    _showGuestUI() {
        document.getElementById('sidebar').hidden = true;
        document.getElementById('sidebar-toggle').hidden = true;

        const authBtn = document.getElementById('auth-btn');
        authBtn.title = 'Se connecter';
        authBtn.innerHTML = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 3h4a2 2 0 012 2v14a2 2 0 01-2 2h-4"/><polyline points="10 17 15 12 10 7"/><line x1="15" y1="12" x2="3" y2="12"/></svg>`;

        // Show guest banner
        document.getElementById('guest-banner').hidden = false;
    },

    async loadConversations() {
        if (!this.state.authenticated) return;
        try {
            const convs = await API.listConversations();
            const list = document.getElementById('conversations-list');
            list.innerHTML = '';

            for (const conv of convs) {
                const item = document.createElement('div');
                item.className = 'conv-item' + (conv.id === Chat.conversationId ? ' active' : '');
                item.dataset.id = conv.id;
                item.innerHTML = `
                    <span class="conv-title">${DOMPurify.sanitize(conv.title)}</span>
                    <button class="conv-delete" title="Supprimer">&times;</button>
                `;

                item.querySelector('.conv-title').addEventListener('click', () => {
                    Chat.loadConversation(conv.id);
                    this.closeSidebar();
                });

                item.querySelector('.conv-delete').addEventListener('click', async (e) => {
                    e.stopPropagation();
                    await API.deleteConversation(conv.id);
                    item.remove();
                    if (Chat.conversationId === conv.id) Chat.newChat();
                });

                list.appendChild(item);
            }
        } catch (e) {
            console.warn('Load conversations failed:', e);
        }
    },

    toggleSidebar() {
        const sidebar = document.getElementById('sidebar');
        const isOpen = sidebar.classList.toggle('open');
        const btn = document.getElementById('sidebar-toggle');
        btn.innerHTML = isOpen
            ? `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`
            : `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12h18M3 6h18M3 18h18"/></svg>`;
    },

    closeSidebar() {
        const sidebar = document.getElementById('sidebar');
        if (sidebar.classList.contains('open')) {
            this.toggleSidebar();
        }
    }
};

// Boot
document.addEventListener('DOMContentLoaded', () => App.init());
