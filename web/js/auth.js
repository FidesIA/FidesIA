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

        // Forgot password
        document.getElementById('forgot-link').addEventListener('click', (e) => {
            e.preventDefault();
            this.showForgotForm();
        });
        document.getElementById('forgot-back').addEventListener('click', (e) => {
            e.preventDefault();
            this.backToLogin();
        });
        document.getElementById('forgot-btn').addEventListener('click', () => this.handleForgotPassword());
        document.getElementById('forgot-email').addEventListener('keydown', (e) => {
            if (e.key === 'Enter') this.handleForgotPassword();
        });
    },

    open() {
        _openModal('auth-modal');
    },

    close() {
        document.getElementById('auth-modal').hidden = true;
        document.getElementById('login-error').hidden = true;
        document.getElementById('register-error').hidden = true;
        document.getElementById('forgot-form').hidden = true;
        document.getElementById('forgot-error').hidden = true;
        document.getElementById('forgot-success').hidden = true;
    },

    switchTab(tab) {
        document.querySelectorAll('.auth-tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tab));
        document.getElementById('login-form').hidden = tab !== 'login';
        document.getElementById('register-form').hidden = tab !== 'register';
        document.getElementById('forgot-form').hidden = true;
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
                API.setToken(data.token);
                API.setUserId(data.user_id);
                API.setDisplayName(data.display_name || '');
                this.close();
                App.onLogin(data);
            } else {
                errDiv.textContent = data.message || 'Identifiants incorrects';
                errDiv.hidden = false;
            }
        } catch (e) {
            errDiv.textContent = e.message || 'Erreur de connexion';
            errDiv.hidden = false;
        } finally {
            document.getElementById('login-password').value = '';
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
                API.setToken(data.token);
                API.setUserId(data.user_id);
                API.setDisplayName(data.display_name || name);
                this.close();
                App.onLogin(data);
            } else {
                errDiv.textContent = data.message || "Erreur lors de l'inscription";
                errDiv.hidden = false;
            }
        } catch (e) {
            errDiv.textContent = e.message || 'Erreur de connexion';
            errDiv.hidden = false;
        } finally {
            document.getElementById('register-password').value = '';
            btn.disabled = false;
            btn.textContent = 'Créer mon compte';
        }
    },

    showForgotForm() {
        document.querySelectorAll('.auth-tab').forEach(t => t.classList.remove('active'));
        document.getElementById('login-form').hidden = true;
        document.getElementById('register-form').hidden = true;
        document.getElementById('forgot-form').hidden = false;
        document.getElementById('forgot-error').hidden = true;
        document.getElementById('forgot-success').hidden = true;
        document.getElementById('forgot-email').value = '';
        document.getElementById('forgot-btn').hidden = false;
    },

    backToLogin() {
        document.getElementById('forgot-form').hidden = true;
        this.switchTab('login');
    },

    async handleForgotPassword() {
        const btn = document.getElementById('forgot-btn');
        const errDiv = document.getElementById('forgot-error');
        const successDiv = document.getElementById('forgot-success');
        const email = document.getElementById('forgot-email').value.trim();

        if (!email) return;

        btn.disabled = true;
        btn.textContent = 'Envoi...';
        errDiv.hidden = true;
        successDiv.hidden = true;

        try {
            const data = await API.forgotPassword(email);
            successDiv.textContent = data.message || 'Si cette adresse est enregistrée, un email a été envoyé.';
            successDiv.hidden = false;
            btn.hidden = true;
        } catch (e) {
            errDiv.textContent = e.message || "Erreur lors de l'envoi";
            errDiv.hidden = false;
        } finally {
            btn.disabled = false;
            btn.textContent = 'Envoyer le lien';
        }
    },

    async checkSession() {
        const token = API.getToken();
        if (!token) return null;

        try {
            const data = await API.checkSession();
            if (data.authenticated) return data;
        } catch (_) { /* invalid session */ }

        API.clearToken();
        return null;
    },

    async logout() {
        Chat.cancelStream();
        await API.logout();
        API.clearToken();
        localStorage.removeItem('fidesia_user_id');
        localStorage.removeItem('fidesia_display_name');
        App.onLogout();
    },
};
