import { Eye, EyeOff } from 'lucide-react'
import { useRef, useState } from 'react'
import { toast } from 'sonner'
import { ActionsProvider } from '@/components/actions'
import { useDotGridBackground } from '@/components/login-background/use-dot-grid-background'
import { Shell } from '@/components/shell'
import { Button } from '@/components/ui/button'
import './login.css'

const DEMO_EMAIL = 'liamszefner@gmail.com'
const DEMO_PASSWORD = 'demo123'

export function DemoEntry() {
  // shortcut: a refresh resets this fake login, replace with real auth when it is required.
  const [signedIn, setSignedIn] = useState(false)
  return signedIn
    ? <ActionsProvider><Shell /></ActionsProvider>
    : <Login onSignIn={() => setSignedIn(true)} />
}

export function Login({ onSignIn }: { onSignIn: () => void }) {
  const canvas = useRef<HTMLCanvasElement>(null)
  const [visible, setVisible] = useState(false)
  const [error, setError] = useState(false)
  useDotGridBackground(canvas)

  return (
    <main className="login-page">
      <div className="login-background" aria-hidden="true">
        <canvas ref={canvas} />
      </div>
      <div className="login-panel">
        <div className="login-heading">
          <div className="login-logo">
            <img src="/favicon.svg" alt="" width="28" height="28" />
          </div>
          <h1>Sign in to Mirage</h1>
        </div>
        <form
          className="login-form"
          autoComplete="off"
          aria-label="Demo sign-in"
          onChange={() => setError(false)}
          onSubmit={(event) => {
            event.preventDefault()
            const fields = new FormData(event.currentTarget)
            if (fields.get('email') !== DEMO_EMAIL || fields.get('password') !== DEMO_PASSWORD) {
              setError(true)
              return
            }
            onSignIn()
          }}
        >
          <div className="login-field">
            <input
              name="email"
              type="email"
              aria-label="Email"
              placeholder="Email"
              defaultValue={DEMO_EMAIL}
              aria-invalid={error || undefined}
              aria-describedby={error ? 'login-error' : undefined}
              autoCapitalize="none"
              spellCheck={false}
              required
            />
          </div>
          <div className="login-password-group">
            <div className="login-field login-password">
              <input
                name="password"
                type={visible ? 'text' : 'password'}
                aria-label="Password"
                placeholder="Password"
                defaultValue={DEMO_PASSWORD}
                aria-invalid={error || undefined}
                aria-describedby={error ? 'login-error' : undefined}
                required
              />
              <button
                type="button"
                className="login-password-toggle"
                aria-label={visible ? 'Hide password' : 'Show password'}
                aria-pressed={visible}
                onClick={() => setVisible((value) => !value)}
              >
                {visible ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
              </button>
            </div>
            <button
              type="button"
              className="login-forgot"
              onClick={() => toast(`Demo login: ${DEMO_EMAIL} / ${DEMO_PASSWORD}`)}
            >
              Forgot your password?
            </button>
          </div>
          {error && <p id="login-error" role="alert" className="text-[#b91c1c]">Incorrect email or password.</p>}
          <div className="login-submit-row">
            <Button type="submit" variant="primary" className="login-submit">Sign in</Button>
          </div>
        </form>
      </div>
    </main>
  )
}
