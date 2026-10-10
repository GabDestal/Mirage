import { Eye, EyeOff } from 'lucide-react'
import { useRef, useState } from 'react'
import { toast } from 'sonner'
import { ActionsProvider } from '@/components/actions'
import { useDotGridBackground } from '@/components/login-background/use-dot-grid-background'
import { Shell } from '@/components/shell'
import { Button } from '@/components/ui/button'
import './login.css'

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
          onSubmit={(event) => {
            event.preventDefault()
            onSignIn()
          }}
        >
          <div className="login-field">
            <input
              name="email"
              type="email"
              aria-label="Email"
              placeholder="Email"
              defaultValue="liamshaffner@gmail.com"
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
                defaultValue="mirage-demo"
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
              onClick={() => toast('Demo sign-in: any email and password works.')}
            >
              Forgot your password?
            </button>
          </div>
          <div className="login-submit-row">
            <Button type="submit" variant="primary" className="login-submit">Sign in</Button>
          </div>
        </form>
      </div>
    </main>
  )
}
