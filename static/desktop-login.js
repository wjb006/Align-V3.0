(() => {
  const form = document.getElementById('desktop-login-form');
  const title = document.getElementById('form-title');
  const kicker = document.getElementById('form-kicker');
  const intro = document.getElementById('form-intro');
  const nameField = document.getElementById('name-field');
  const nameInput = document.getElementById('display-name');
  const password = document.getElementById('password');
  const passwordHint = document.getElementById('password-hint');
  const message = document.getElementById('login-message');
  const button = document.getElementById('submit-button');
  let setupRequired = false;
  let recoveryMode = false;
  const recoveryToggle = document.getElementById('recovery-toggle');

  async function request(path, body) {
    const response = await fetch(path, {
      method: 'POST', credentials: 'same-origin', cache: 'no-store',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || `Sign-in failed (${response.status}).`);
    return payload;
  }

  async function initialise() {
    try {
      const response = await fetch('/api/local-auth/status', { credentials: 'same-origin', cache: 'no-store' });
      const status = await response.json();
      if (status.authenticated) { location.replace('/desktop'); return; }
      setupRequired = status.setup_required === true;
      if (setupRequired) {
        kicker.textContent = 'FIRST-TIME SETUP';
        title.textContent = 'Create your workspace';
        intro.textContent = 'Set up the local Owner account for this computer.';
        nameField.hidden = false;
        nameInput.required = true;
        password.autocomplete = 'new-password';
        passwordHint.hidden = false;
        button.textContent = 'Create account';
      }
    } catch (error) {
      message.textContent = error.message || 'Align could not check the local sign-in status.';
      button.disabled = true;
    }
  }

  recoveryToggle.addEventListener('click', () => {
    if (setupRequired) return;
    recoveryMode = !recoveryMode;
    message.textContent = '';
    title.textContent = recoveryMode ? 'Reset local password' : 'Welcome back';
    kicker.textContent = recoveryMode ? 'THIS COMPUTER ONLY' : 'YOUR WORKSPACE';
    intro.textContent = recoveryMode
      ? 'Set a new password for the local Owner account on this computer. Your planner data will remain untouched.'
      : 'Sign in to continue to your Align workspace.';
    password.autocomplete = recoveryMode ? 'new-password' : 'current-password';
    password.value = '';
    passwordHint.hidden = !recoveryMode;
    recoveryToggle.textContent = recoveryMode ? 'Back to sign in' : 'Forgot your local password?';
    button.textContent = recoveryMode ? 'Reset password' : 'Sign in';
  });

  form.addEventListener('submit', async event => {
    event.preventDefault();
    message.textContent = '';
    if (!form.reportValidity()) return;
    button.disabled = true;
    button.textContent = setupRequired ? 'Creating account…' : (recoveryMode ? 'Resetting password…' : 'Signing in…');
    const body = {
      email: document.getElementById('email').value.trim(),
      password: password.value,
      remember: document.getElementById('remember').checked,
    };
    if (setupRequired) body.display_name = nameInput.value.trim();
    if (recoveryMode) {
      const confirmed = window.confirm(
        'Reset the local Owner password on this computer? This signs out all remembered sessions. Your planner data and settings will not be deleted.'
      );
      if (!confirmed) {
        button.disabled = false;
        button.textContent = 'Reset password';
        return;
      }
      body.confirmation = 'RESET LOCAL OWNER';
    }
    try {
      if (recoveryMode) {
        await request('/api/local-auth/reset-password', body);
        recoveryMode = false;
        password.value = '';
        passwordHint.hidden = true;
        title.textContent = 'Password updated';
        intro.textContent = 'Your local password has been changed. Sign in with your new password.';
        recoveryToggle.textContent = 'Forgot your local password?';
        button.disabled = false;
        button.textContent = 'Sign in';
        message.textContent = 'Password updated successfully.';
        return;
      }
      await request(setupRequired ? '/api/local-auth/setup' : '/api/local-auth/login', body);
      location.replace('/desktop');
    } catch (error) {
      message.textContent = error.message || 'Unable to sign in.';
      button.disabled = false;
      button.textContent = setupRequired ? 'Create account' : (recoveryMode ? 'Reset password' : 'Sign in');
    }
  });

  void initialise();
})();
