'use client';

import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import Link from 'next/link';
import {
  ApiError,
  confirmSignup,
  errMsg,
  forgotPassword,
  loginAccount,
  registerAccount,
  resendSignupOtp,
  resetPassword,
  setToken,
} from '@/lib/api';
import ThemeToggle from '@/components/ThemeToggle';

type AuthStep = 'signin' | 'register' | 'verify_signup' | 'forgot_email' | 'forgot_reset';

export default function LoginPage() {
  const [step, setStep] = useState<AuthStep>('signin');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [org, setOrg] = useState('');
  const [otpCode, setOtpCode] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [cooldown, setCooldown] = useState(0);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [needsVerifyHint, setNeedsVerifyHint] = useState(false);

  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = setTimeout(() => setCooldown((c) => Math.max(0, c - 1)), 1000);
    return () => clearTimeout(timer);
  }, [cooldown]);

  function switchTab(next: 'signin' | 'register') {
    setStep(next);
    setError(null);
    setNotice(null);
    setNeedsVerifyHint(false);
    setOtpCode('');
  }

  async function handleSignIn(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    setNeedsVerifyHint(false);
    try {
      const res = await loginAccount(email, password);
      setToken(res.access_token);
      window.location.href = '/dashboard';
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        setNeedsVerifyHint(true);
      }
      setError(errMsg(err));
      setBusy(false);
    }
  }

  async function handleRegister(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await registerAccount(email, password, org);
      setOtpCode('');
      setCooldown(60);
      setNotice(`We sent a 6-digit verification code to ${email.trim().toLowerCase()}.`);
      setStep('verify_signup');
    } catch (err) {
      setError(errMsg(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleConfirmSignup(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await confirmSignup(email, otpCode.trim());
      setToken(res.access_token);
      window.location.href = '/dashboard';
    } catch (err) {
      setError(errMsg(err));
      setBusy(false);
    }
  }

  async function handleResendSignup() {
    if (cooldown > 0 || busy) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await resendSignupOtp(email);
      setCooldown(60);
      setNotice(`A fresh 6-digit verification code was sent to ${email.trim().toLowerCase()}.`);
    } catch (err) {
      setError(errMsg(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleForgotEmail(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await forgotPassword(email);
      setOtpCode('');
      setNewPassword('');
      setNotice('If an account exists for that email, a 6-digit reset code has been sent.');
      setStep('forgot_reset');
    } catch (err) {
      setError(errMsg(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleResetPassword(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await resetPassword(email, otpCode.trim(), newPassword);
      setToken(res.access_token);
      window.location.href = '/dashboard';
    } catch (err) {
      setError(errMsg(err));
      setBusy(false);
    }
  }

  const inputCls =
    'w-full rounded-xl border border-black/[0.08] bg-[#F5F5F7] px-3.5 py-2.5 text-sm text-[#1D1D1F] placeholder-[#6E6E73]/70 focus:border-[#0071E3] focus:bg-white focus:outline-none dark:border-white/[0.08] dark:bg-[#2C2C2E] dark:text-[#F5F5F7] dark:placeholder-[#8E8E93] dark:focus:border-[#0A84FF]';

  const primaryBtnCls =
    'inline-flex w-full items-center justify-center rounded-full bg-[#0071E3] px-5 py-2.5 text-sm font-medium text-white transition hover:bg-[#0077ED] disabled:cursor-not-allowed disabled:opacity-50 dark:bg-[#0A84FF] dark:hover:bg-[#2E96FF]';

  return (
    <main className="flex min-h-screen flex-col justify-center bg-[#F5F5F7] px-4 py-12 text-[#1D1D1F] transition-colors dark:bg-[#000000] dark:text-[#F5F5F7]">
      <div className="mx-auto w-full max-w-[420px]">
        <div className="mb-6 flex items-center justify-between">
          <Link
            href="/"
            className="text-lg font-semibold tracking-[-0.02em] text-[#1D1D1F] dark:text-[#F5F5F7]"
          >
            StarkEven
          </Link>
          <ThemeToggle />
        </div>

        <div className="rounded-3xl border border-black/[0.06] bg-white p-6 shadow-[0_2px_12px_rgba(0,0,0,0.04)] dark:border-white/[0.08] dark:bg-[#1C1C1E] dark:shadow-none sm:p-8">
          {(step === 'signin' || step === 'register') && (
            <div className="mb-6 grid grid-cols-2 rounded-full border border-black/[0.06] bg-[#F5F5F7] p-1 dark:border-white/[0.08] dark:bg-[#2C2C2E]">
              <button
                type="button"
                onClick={() => switchTab('signin')}
                data-testid="tab-signin"
                className={`rounded-full py-1.5 text-xs font-medium transition ${
                  step === 'signin'
                    ? 'bg-white text-[#1D1D1F] shadow-sm dark:bg-[#1C1C1E] dark:text-[#F5F5F7]'
                    : 'text-[#6E6E73] hover:text-[#1D1D1F] dark:text-[#8E8E93] dark:hover:text-[#F5F5F7]'
                }`}
              >
                Sign In
              </button>
              <button
                type="button"
                onClick={() => switchTab('register')}
                data-testid="tab-register"
                className={`rounded-full py-1.5 text-xs font-medium transition ${
                  step === 'register'
                    ? 'bg-white text-[#1D1D1F] shadow-sm dark:bg-[#1C1C1E] dark:text-[#F5F5F7]'
                    : 'text-[#6E6E73] hover:text-[#1D1D1F] dark:text-[#8E8E93] dark:hover:text-[#F5F5F7]'
                }`}
              >
                Create Account
              </button>
            </div>
          )}

          {notice && (
            <p className="mb-4 rounded-2xl border border-[#0071E3]/20 bg-[#0071E3]/10 px-3.5 py-2.5 text-xs leading-relaxed text-[#0071E3] dark:border-[#0A84FF]/25 dark:bg-[#0A84FF]/15 dark:text-[#0A84FF]">
              {notice}
            </p>
          )}
          {error && (
            <div className="mb-4 rounded-2xl border border-[#FF3B30]/25 bg-[#FF3B30]/10 px-3.5 py-2.5 text-xs leading-relaxed text-[#D70015] dark:text-[#FF453A]">
              <p>{error}</p>
              {needsVerifyHint && (
                <button
                  type="button"
                  onClick={() => {
                    setError(null);
                    setNeedsVerifyHint(false);
                    setStep('verify_signup');
                    void handleResendSignup();
                  }}
                  className="mt-1.5 font-semibold underline"
                >
                  Enter verification code or resend OTP
                </button>
              )}
            </div>
          )}

          {step === 'signin' && (
            <form onSubmit={(e) => void handleSignIn(e)} className="space-y-4">
              <div>
                <h1 className="text-xl font-semibold tracking-[-0.02em]">Welcome back</h1>
                <p className="mt-1 text-xs text-[#6E6E73] dark:text-[#8E8E93]">
                  Sign in to your StarkEven workspace.
                </p>
              </div>
              <div>
                <label htmlFor="signin-email" className="mb-1.5 block text-xs font-medium text-[#6E6E73] dark:text-[#8E8E93]">
                  Work Email
                </label>
                <input
                  id="signin-email"
                  className={inputCls}
                  type="email"
                  placeholder="you@company.com"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>
              <div>
                <div className="mb-1.5 flex items-center justify-between">
                  <label htmlFor="signin-password" className="text-xs font-medium text-[#6E6E73] dark:text-[#8E8E93]">
                    Password
                  </label>
                  <button
                    type="button"
                    data-testid="forgot-password-link"
                    onClick={() => {
                      setError(null);
                      setNotice(null);
                      setStep('forgot_email');
                    }}
                    className="text-xs font-medium text-[#0071E3] hover:underline dark:text-[#0A84FF]"
                  >
                    Forgot password?
                  </button>
                </div>
                <input
                  id="signin-password"
                  className={inputCls}
                  type="password"
                  placeholder="Enter password"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>
              <button type="submit" className={primaryBtnCls} disabled={busy}>
                {busy ? 'Signing in…' : 'Sign in'}
              </button>
            </form>
          )}

          {step === 'register' && (
            <form onSubmit={(e) => void handleRegister(e)} className="space-y-4">
              <div>
                <h1 className="text-xl font-semibold tracking-[-0.02em]">Create your account</h1>
                <p className="mt-1 text-xs text-[#6E6E73] dark:text-[#8E8E93]">
                  Verify your email to unlock 50 free trial credits.
                </p>
              </div>
              <div>
                <label htmlFor="reg-org" className="mb-1.5 block text-xs font-medium text-[#6E6E73] dark:text-[#8E8E93]">
                  Organization Name
                </label>
                <input
                  id="reg-org"
                  className={inputCls}
                  placeholder="Company name"
                  required
                  value={org}
                  onChange={(e) => setOrg(e.target.value)}
                />
              </div>
              <div>
                <label htmlFor="reg-email" className="mb-1.5 block text-xs font-medium text-[#6E6E73] dark:text-[#8E8E93]">
                  Work Email
                </label>
                <input
                  id="reg-email"
                  className={inputCls}
                  type="email"
                  placeholder="you@company.com"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>
              <div>
                <label htmlFor="reg-password" className="mb-1.5 block text-xs font-medium text-[#6E6E73] dark:text-[#8E8E93]">
                  Password
                </label>
                <input
                  id="reg-password"
                  className={inputCls}
                  type="password"
                  placeholder="Minimum 8 characters"
                  autoComplete="new-password"
                  required
                  minLength={8}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>
              <button type="submit" className={primaryBtnCls} disabled={busy}>
                {busy ? 'Creating account…' : 'Create account (50 free credits)'}
              </button>
            </form>
          )}

          {step === 'verify_signup' && (
            <form onSubmit={(e) => void handleConfirmSignup(e)} className="space-y-5">
              <div>
                <h1 className="text-xl font-semibold tracking-[-0.02em]">Verify your email</h1>
                <p className="mt-1 text-xs text-[#6E6E73] dark:text-[#8E8E93]">
                  Enter the 6-digit code sent to <strong className="font-medium text-[#1D1D1F] dark:text-[#F5F5F7]">{email}</strong>.
                </p>
              </div>
              <div>
                <label htmlFor="signup-otp" className="mb-1.5 block text-xs font-medium text-[#6E6E73] dark:text-[#8E8E93]">
                  6-Digit Verification Code
                </label>
                <input
                  id="signup-otp"
                  data-testid="signup-otp-input"
                  className={`${inputCls} text-center font-mono text-2xl font-semibold tracking-[0.35em] tabular-nums`}
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  maxLength={6}
                  pattern="\d{6}"
                  placeholder="••••••"
                  required
                  value={otpCode}
                  onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                />
              </div>
              <button type="submit" className={primaryBtnCls} disabled={busy || otpCode.length !== 6}>
                {busy ? 'Verifying…' : 'Verify & Unlock 50 Credits'}
              </button>
              <div className="flex items-center justify-between pt-1 text-xs">
                <button
                  type="button"
                  data-testid="resend-otp-btn"
                  disabled={cooldown > 0 || busy}
                  onClick={() => void handleResendSignup()}
                  className="font-medium tabular-nums text-[#0071E3] hover:underline disabled:cursor-not-allowed disabled:text-[#6E6E73] dark:text-[#0A84FF] dark:disabled:text-[#8E8E93]"
                >
                  {cooldown > 0 ? `Resend code (${cooldown}s)` : 'Resend code'}
                </button>
                <button
                  type="button"
                  onClick={() => switchTab('signin')}
                  className="text-[#6E6E73] hover:text-[#1D1D1F] dark:text-[#8E8E93] dark:hover:text-[#F5F5F7]"
                >
                  Back to sign in
                </button>
              </div>
            </form>
          )}

          {step === 'forgot_email' && (
            <form onSubmit={(e) => void handleForgotEmail(e)} className="space-y-4">
              <div>
                <h1 className="text-xl font-semibold tracking-[-0.02em]">Reset password</h1>
                <p className="mt-1 text-xs text-[#6E6E73] dark:text-[#8E8E93]">
                  Step 1 of 2 · Enter your account email to receive a 6-digit verification code.
                </p>
              </div>
              <div>
                <label htmlFor="forgot-email" className="mb-1.5 block text-xs font-medium text-[#6E6E73] dark:text-[#8E8E93]">
                  Account Email
                </label>
                <input
                  id="forgot-email"
                  data-testid="forgot-email-input"
                  className={inputCls}
                  type="email"
                  placeholder="you@company.com"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>
              <button type="submit" className={primaryBtnCls} disabled={busy}>
                {busy ? 'Sending code…' : 'Send reset code'}
              </button>
              <button
                type="button"
                onClick={() => switchTab('signin')}
                className="w-full text-center text-xs text-[#6E6E73] hover:text-[#1D1D1F] dark:text-[#8E8E93] dark:hover:text-[#F5F5F7]"
              >
                Back to sign in
              </button>
            </form>
          )}

          {step === 'forgot_reset' && (
            <form onSubmit={(e) => void handleResetPassword(e)} className="space-y-4">
              <div>
                <h1 className="text-xl font-semibold tracking-[-0.02em]">Choose new password</h1>
                <p className="mt-1 text-xs text-[#6E6E73] dark:text-[#8E8E93]">
                  Step 2 of 2 · Enter the 6-digit code sent to <strong className="font-medium text-[#1D1D1F] dark:text-[#F5F5F7]">{email}</strong>.
                </p>
              </div>
              <div>
                <label htmlFor="reset-otp" className="mb-1.5 block text-xs font-medium text-[#6E6E73] dark:text-[#8E8E93]">
                  6-Digit Verification Code
                </label>
                <input
                  id="reset-otp"
                  data-testid="reset-otp-input"
                  className={`${inputCls} text-center font-mono text-xl font-semibold tracking-[0.35em] tabular-nums`}
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  maxLength={6}
                  pattern="\d{6}"
                  placeholder="••••••"
                  required
                  value={otpCode}
                  onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                />
              </div>
              <div>
                <label htmlFor="reset-password" className="mb-1.5 block text-xs font-medium text-[#6E6E73] dark:text-[#8E8E93]">
                  New Password
                </label>
                <input
                  id="reset-password"
                  data-testid="reset-new-password"
                  className={inputCls}
                  type="password"
                  placeholder="Minimum 8 characters"
                  autoComplete="new-password"
                  required
                  minLength={8}
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                />
              </div>
              <button type="submit" className={primaryBtnCls} disabled={busy || otpCode.length !== 6}>
                {busy ? 'Updating password…' : 'Reset Password & Sign In'}
              </button>
              <button
                type="button"
                onClick={() => switchTab('signin')}
                className="w-full text-center text-xs text-[#6E6E73] hover:text-[#1D1D1F] dark:text-[#8E8E93] dark:hover:text-[#F5F5F7]"
              >
                Back to sign in
              </button>
            </form>
          )}
        </div>
      </div>
    </main>
  );
}
