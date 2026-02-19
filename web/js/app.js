/**
 * App — Init, state, routing
 */
const EXAMPLE_QUESTIONS = [
    { q: "Qu'est-ce que la Trinité ?", label: "La Trinité" },
    { q: "Que dit l'Église sur la dignité humaine ?", label: "Dignité humaine" },
    { q: "Quels sont les 7 sacrements ?", label: "Les 7 sacrements" },
    { q: "Qu'est-ce que l'Eucharistie ?", label: "L'Eucharistie" },
    { q: "Comment l'Église définit-elle le péché originel ?", label: "Péché originel" },
    { q: "Que signifie la Résurrection du Christ ?", label: "La Résurrection" },
    { q: "Qu'est-ce que la grâce sanctifiante ?", label: "La grâce" },
    { q: "Quel est le rôle de la Vierge Marie dans la foi catholique ?", label: "La Vierge Marie" },
    { q: "Que dit le Magistère sur la liberté religieuse ?", label: "Liberté religieuse" },
    { q: "Qu'est-ce que la doctrine sociale de l'Église ?", label: "Doctrine sociale" },
    { q: "Quels sont les dix commandements ?", label: "Les 10 commandements" },
    { q: "Qu'est-ce que le sacrement de réconciliation ?", label: "La réconciliation" },
    { q: "Comment prier le rosaire ?", label: "Le rosaire" },
    { q: "Que dit l'Église sur le mariage ?", label: "Le mariage" },
    { q: "Qu'est-ce que l'infaillibilité pontificale ?", label: "Infaillibilité pontificale" },
    { q: "Quelle est la différence entre dogme et doctrine ?", label: "Dogme et doctrine" },
    { q: "Que sont les vertus théologales ?", label: "Vertus théologales" },
    { q: "Qu'est-ce que la communion des saints ?", label: "Communion des saints" },
    { q: "Que dit l'Église sur la fin des temps ?", label: "Eschatologie" },
    { q: "Qu'est-ce que le Credo de Nicée-Constantinople ?", label: "Le Credo" },
    { q: "Quel est le sens du Carême ?", label: "Le Carême" },
    { q: "Qu'est-ce que la liturgie des Heures ?", label: "Liturgie des Heures" },
    { q: "Que dit l'Église sur la bioéthique ?", label: "Bioéthique" },
    { q: "Qu'est-ce que la Tradition apostolique ?", label: "Tradition apostolique" },
    { q: "Quel est le rôle des anges dans la foi catholique ?", label: "Les anges" },
    { q: "Que signifie l'Ascension du Christ ?", label: "L'Ascension" },
    { q: "Qu'est-ce que le purgatoire ?", label: "Le purgatoire" },
    { q: "Comment l'Église comprend-elle la souffrance ?", label: "Sens de la souffrance" },
    { q: "Que dit l'Église sur la justice et la paix ?", label: "Justice et paix" },
    { q: "Qu'est-ce que la vocation sacerdotale ?", label: "Vocation sacerdotale" },
];

const Donation = {
    _count: 0,
    _shown: false,

    onExchange() {
        this._count++;
        if (this._count >= 5 && !this._shown && !sessionStorage.getItem('fidesia_donate_dismissed')) {
            this._shown = true;
            document.getElementById('donate-modal').hidden = false;
        }
    },

    close() {
        document.getElementById('donate-modal').hidden = true;
        sessionStorage.setItem('fidesia_donate_dismissed', '1');
    }
};

const App = {
    state: {
        authenticated: false,
        userId: null,
        displayName: '',
    },

    async init() {
        // Random example questions
        this._populateExamples();

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

        // Load conversations and saint du jour
        this.loadConversations();
        Saints.init();
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
    },

    _populateExamples() {
        const container = document.getElementById('welcome-examples');
        const shuffled = [...EXAMPLE_QUESTIONS].sort(() => Math.random() - 0.5);
        const picked = shuffled.slice(0, 3);
        for (const ex of picked) {
            const btn = document.createElement('button');
            btn.className = 'example-btn';
            btn.dataset.q = ex.q;
            btn.textContent = ex.label;
            container.appendChild(btn);
        }
    }
};

// Boot
App._populateExamples();
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => App.init());
} else {
    App.init();
}
