import { useState } from 'react'

type LoginPageProps = {
  busy: boolean
  onSubmit: (credentials: { username: string; password: string }) => Promise<void>
}

export function LoginPage({ busy, onSubmit }: LoginPageProps) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')

  return (
    <main className="login-shell">
      <section className="login-card">
        <p className="eyebrow">Access</p>
        <h1>Sign in to CMCTrans</h1>
        <p className="login-copy">
          Use your workspace account to access translation jobs, shared knowledge, and admin tools.
        </p>

        <form
          className="login-form"
          onSubmit={(event) => {
            event.preventDefault()
            void onSubmit({ username, password })
          }}
        >
          <label className="field">
            <span>Username</span>
            <input
              type="text"
              value={username}
              autoComplete="username"
              disabled={busy}
              onChange={(event) => setUsername(event.target.value)}
            />
          </label>

          <label className="field">
            <span>Password</span>
            <input
              type="password"
              value={password}
              autoComplete="current-password"
              disabled={busy}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>

          <button type="submit" className="primary-button login-submit" disabled={busy}>
            {busy ? 'Signing in...' : 'Sign in'}
          </button>
        </form>
      </section>
    </main>
  )
}
