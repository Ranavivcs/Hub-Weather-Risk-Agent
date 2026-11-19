import { useEffect, useRef, useState } from 'react'

// Minimal typing for the browser's Web Speech API (not in TypeScript's DOM lib in all versions).
interface RecognitionResultEvent {
  resultIndex: number
  results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }>
}
interface Recognition {
  lang: string
  interimResults: boolean
  continuous: boolean
  onresult: ((e: RecognitionResultEvent) => void) | null
  onend: (() => void) | null
  onerror: ((e: { error: string }) => void) | null
  start(): void
  stop(): void
}
type RecognitionCtor = new () => Recognition

function recognitionCtor(): RecognitionCtor | undefined {
  const w = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor }
  return w.SpeechRecognition ?? w.webkitSpeechRecognition
}

/** Speech-to-text into a text box. The transcript goes to `onText`; nothing is sent automatically. */
export function useSpeechInput(onText: (text: string) => void) {
  const supported = recognitionCtor() !== undefined
  const [listening, setListening] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const recognitionRef = useRef<Recognition | null>(null)

  useEffect(() => () => recognitionRef.current?.stop(), []) // stop the mic if the component unmounts

  function start(prefix: string) {
    const Ctor = recognitionCtor()
    if (!Ctor || listening) return
    const rec = new Ctor()
    rec.lang = 'en-US'
    rec.interimResults = true // show words while speaking
    rec.continuous = false    // stop after a pause
    rec.onresult = (e) => {
      let transcript = ''
      for (let i = 0; i < e.results.length; i++) transcript += e.results[i][0].transcript
      onText((prefix ? prefix + ' ' : '') + transcript.trim())
    }
    rec.onerror = (e) => setError(e.error === 'not-allowed' ? 'Microphone access was blocked.' : `Voice input failed (${e.error}).`)
    rec.onend = () => setListening(false)
    recognitionRef.current = rec
    setError(null)
    setListening(true)
    rec.start()
  }

  function stop() {
    recognitionRef.current?.stop()
  }

  return { supported, listening, error, start, stop }
}
