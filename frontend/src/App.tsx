import { useEffect, useRef, useState } from "react";
import { decodeFile, encodeText } from "./api";

type Phase = "idle" | "loading" | "success" | "error";

export default function App(): JSX.Element {
  const [text, setText] = useState("Hello from AudioLink");
  const [encodePhase, setEncodePhase] = useState<Phase>("idle");
  const [decodePhase, setDecodePhase] = useState<Phase>("idle");
  const [encodeError, setEncodeError] = useState<string | null>(null);
  const [decodeError, setDecodeError] = useState<string | null>(null);
  const [decodedText, setDecodedText] = useState<string>("");
  const [audioUrl, setAudioUrl] = useState<string>("");
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    return () => {
      if (audioUrl) {
        URL.revokeObjectURL(audioUrl);
      }
    };
  }, [audioUrl]);

  const handleEncode = async () => {
    setEncodePhase("loading");
    setEncodeError(null);
    try {
      const { blobUrl } = await encodeText(text);
      if (audioUrl) {
        URL.revokeObjectURL(audioUrl);
      }
      setAudioUrl(blobUrl);
      setEncodePhase("success");
      requestAnimationFrame(() => {
        audioRef.current?.load();
        audioRef.current?.play().catch(() => {
          /* autoplay may be blocked; ignore */
        });
      });
    } catch (error) {
      setEncodePhase("error");
      setEncodeError(error instanceof Error ? error.message : String(error));
    }
  };

  const handleDecode = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const file = form.get("file");
    if (!(file instanceof File) || file.size === 0) {
      setDecodeError("Please choose a WAV file first.");
      setDecodePhase("error");
      return;
    }

    setDecodePhase("loading");
    setDecodeError(null);
    try {
      const text = await decodeFile(file);
      setDecodedText(text);
      setDecodePhase("success");
    } catch (error) {
      setDecodePhase("error");
      setDecodeError(error instanceof Error ? error.message : String(error));
    }
  };

  return (
    <div className="page">
      <header>
        <h1>AudioLink POC</h1>
        <p>Test the FastAPI encode/decode endpoints directly from your browser.</p>
      </header>

      <section>
        <h2>Encode text into audio</h2>
        <label className="field">
          <span>Message</span>
          <textarea
            value={text}
            onChange={(event) => setText(event.target.value)}
            rows={3}
          />
        </label>
        <button onClick={handleEncode} disabled={encodePhase === "loading"}>
          {encodePhase === "loading" ? "Encoding…" : "Generate audio"}
        </button>
        {encodeError && <p className="error">{encodeError}</p>}
        {audioUrl && (
          <div className="result">
            <audio controls ref={audioRef}>
              <source src={audioUrl} type="audio/wav" />
              Your browser does not support the audio element.
            </audio>
            <a href={audioUrl} download="link.wav">
              Download WAV
            </a>
          </div>
        )}
      </section>

      <section>
        <h2>Decode audio back to text</h2>
        <form className="decode" onSubmit={handleDecode}>
          <label className="field">
            <span>Upload WAV file</span>
            <input type="file" name="file" accept="audio/wav" required />
          </label>
          <button type="submit" disabled={decodePhase === "loading"}>
            {decodePhase === "loading" ? "Decoding…" : "Decode"}
          </button>
        </form>
        {decodeError && <p className="error">{decodeError}</p>}
        {decodedText && (
          <div className="result">
            <h3>Decoded message</h3>
            <pre>{decodedText}</pre>
          </div>
        )}
      </section>

      <footer>
        <p>
          Backend URL: <code>{import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000"}</code>
        </p>
      </footer>
    </div>
  );
}
