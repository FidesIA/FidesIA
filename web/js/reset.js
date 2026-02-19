/**
 * Reset password — Standalone page logic
 */
(function () {
    const params = new URLSearchParams(window.location.search);
    const token = params.get('token');

    if (!token) {
        document.getElementById('reset-form-container').hidden = true;
        document.getElementById('reset-invalid').hidden = false;
        return;
    }

    const btn = document.getElementById('reset-btn');
    const errDiv = document.getElementById('reset-error');

    btn.addEventListener('click', handleReset);

    document.getElementById('reset-confirm').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') handleReset();
    });

    document.getElementById('reset-password').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            document.getElementById('reset-confirm').focus();
        }
    });

    async function handleReset() {
        const password = document.getElementById('reset-password').value;
        const confirm = document.getElementById('reset-confirm').value;

        errDiv.hidden = true;

        if (password.length < 6) {
            errDiv.textContent = 'Le mot de passe doit faire au moins 6 caractères';
            errDiv.hidden = false;
            return;
        }

        if (password !== confirm) {
            errDiv.textContent = 'Les mots de passe ne correspondent pas';
            errDiv.hidden = false;
            return;
        }

        btn.disabled = true;
        btn.textContent = 'Modification...';

        try {
            const res = await fetch('/auth/reset-password', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token, password }),
            });
            const data = await res.json();

            if (data.success) {
                document.getElementById('reset-form-container').hidden = true;
                document.getElementById('reset-success').hidden = false;
            } else {
                errDiv.textContent = data.message || 'Erreur lors de la modification';
                errDiv.hidden = false;
            }
        } catch (e) {
            errDiv.textContent = 'Erreur de connexion au serveur';
            errDiv.hidden = false;
        } finally {
            btn.disabled = false;
            btn.textContent = 'Modifier mon mot de passe';
        }
    }
})();
