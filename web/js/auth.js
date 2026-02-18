/**
 * Auth UI — Login/Register modal
 */
const AuthUI = {
    init() {
        // Tab switching
        document.querySelectorAll('.auth-tab').forEach(tab => {
            tab.addEventListener('click', () => this.switchTab(tab.dataset.tab));
        });

        // Login form
        document.getElementById('login-form').addEventListener('submit', (e) => {
            e.preventDefault();
            this.handleLogin();
        });

        // Register form
        document.getElementById('register-form').addEventListener('submit', (e) => {
            e.preventDefault();
            this.handleRegister();
        });

        // Backdrop close
        document.querySelector('#auth-modal .modal-backdrop').addEventListener('click', () => this.close());
    },

    open() {
        document.getElementById('auth-modal').hidden = false;
    },

    close() {
        document.getElementById('auth-modal').hidden = true;
        // Clear errors
        document.getElementById('login-error').hidden = true;
        document.getElementById('register-error').hidden = true;
    },

    switchTab(tab) {
        document.querySelectorAll('.auth-tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tab));
        document.getElementById('login-form').hidden = tab !== 'login';
        document.getElementById('register-form').hidden = tab !== 'register';
    },

    async handleLogin() {
        const btn = document.getElementById('login-btn');
        const errDiv = document.getElementById('login-error');
        const email = document.getElementById('login-email').value.trim();
        const password = document.getElementById('login-password').value;

        if (!email || !password) return;

        btn.disabled = true;
        btn.textContent = 'Connexion...';
        errDiv.hidden = true;

        try {
            const data = await API.login(email, password);
            if (data.success && data.token) {
                document.getElementById('login-password').value = '';
                API.setToken(data.token);
                API.setUserId(data.user_id);
                API.setDisplayName(data.display_name || '');
                this.close();
                App.onLogin(data);
            } else {
                errDiv.textContent = data.message || 'Identifiants incorrects';
                errDiv.hidden = false;
                document.getElementById('login-password').value = '';
            }
        } catch (e) {
            errDiv.textContent = e.message || 'Erreur de connexion';
            errDiv.hidden = false;
            document.getElementById('login-password').value = '';
        } finally {
            btn.disabled = false;
            btn.textContent = 'Se connecter';
        }
    },

    async handleRegister() {
        const btn = document.getElementById('register-btn');
        const errDiv = document.getElementById('register-error');
        const name = document.getElementById('register-name').value.trim();
        const email = document.getElementById('register-email').value.trim();
        const password = document.getElementById('register-password').value;

        if (!name || !email || !password) return;

        btn.disabled = true;
        btn.textContent = 'Inscription...';
        errDiv.hidden = true;

        try {
            const data = await API.register(email, password, name);
            if (data.success && data.token) {
                document.getElementById('register-password').value = '';
                API.setToken(data.token);
                API.setUserId(data.user_id);
                API.setDisplayName(data.display_name || name);
                this.close();
                App.onLogin(data);
            } else {
                errDiv.textContent = data.message || 'Erreur lors de l\'inscription';
                errDiv.hidden = false;
            }
        } catch (e) {
            errDiv.textContent = e.message || 'Erreur de connexion';
            errDiv.hidden = false;
        } finally {
            btn.disabled = false;
            btn.textContent = 'Créer mon compte';
        }
    },

    async checkSession() {
        const token = API.getToken();
        if (!token) return false;

        try {
            const data = await API.checkSession();
            if (data.authenticated) {
                return data;
            }
        } catch (e) { /* invalid session */ }

        API.clearToken();
        return false;
    },

    async logout() {
        Chat.cancelStream();
        await API.logout();
        API.clearToken();
        localStorage.removeItem('fidesia_user_id');
        localStorage.removeItem('fidesia_display_name');
        App.onLogout();
    }
};
