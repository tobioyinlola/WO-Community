import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";

/** The parts of YouTube's player we use. */
interface YTPlayer {
  getCurrentTime(): number;
  seekTo(seconds: number, allowSeekAhead: boolean): void;
  playVideo(): void;
  destroy(): void;
}
interface YTApi {
  Player: new (
    element: HTMLElement,
    options: {
      videoId: string;
      host: string;
      playerVars: Record<string, string | number>;
      events: { onStateChange: (event: { data: number }) => void; onReady: () => void };
    },
  ) => YTPlayer;
}
declare global {
  interface Window {
    YT?: YTApi;
    onYouTubeIframeAPIReady?: () => void;
  }
}

let loading: Promise<YTApi> | null = null;

/** Loads YouTube's player script once for the whole app. */
function loadApi(): Promise<YTApi> {
  if (window.YT?.Player) return Promise.resolve(window.YT);
  loading ??= new Promise<YTApi>((resolve, reject) => {
    const previous = window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady = () => {
      previous?.();
      if (window.YT) resolve(window.YT);
    };
    const script = document.createElement("script");
    script.src = "https://www.youtube.com/iframe_api";
    script.async = true;
    script.onerror = () => {
      loading = null;
      reject(new Error("The video player could not be loaded."));
    };
    document.head.appendChild(script);
  });
  return loading;
}

export interface PlayerHandle {
  time: () => number;
  seek: (seconds: number) => void;
}

interface Props {
  videoId: string;
  title: string;
  /** Where to start, in seconds, so a learner resumes where they left off. */
  start?: number;
  /** Called every so often while playing and when paused, with the position in seconds. */
  onPosition?: (seconds: number) => void;
  onEnded?: () => void;
}

const REPORT_EVERY_MS = 15_000;

/**
 * An embedded YouTube video on the privacy enhanced host, with `rel=0` so it does not suggest other
 * channels afterwards. It reports where the learner is, and when the video ends.
 */
export const YouTubePlayer = forwardRef<PlayerHandle, Props>(function YouTubePlayer({ videoId, title, start = 0, onPosition, onEnded }, ref) {
  const host = useRef<HTMLDivElement>(null);
  const player = useRef<YTPlayer | null>(null);
  const timer = useRef<number>();
  // Keep the latest callbacks without rebuilding the player each time they change.
  const callbacks = useRef({ onPosition, onEnded });
  callbacks.current = { onPosition, onEnded };

  useImperativeHandle(ref, () => ({
    time: () => player.current?.getCurrentTime() ?? 0,
    seek: (seconds) => {
      player.current?.seekTo(seconds, true);
      player.current?.playVideo();
    },
  }));

  useEffect(() => {
    let cancelled = false;
    const stop = () => window.clearInterval(timer.current);
    const report = () => {
      if (player.current) callbacks.current.onPosition?.(Math.floor(player.current.getCurrentTime()));
    };
    void loadApi()
      .then((YT) => {
        if (cancelled || !host.current) return;
        const target = document.createElement("div");
        host.current.replaceChildren(target);
        player.current = new YT.Player(target, {
          videoId,
          host: "https://www.youtube-nocookie.com",
          playerVars: { rel: 0, modestbranding: 1, playsinline: 1, enablejsapi: 1, start: Math.floor(start), origin: window.location.origin },
          events: {
            onReady: () => {
              const frame = host.current?.querySelector("iframe");
              frame?.setAttribute("title", title);
            },
            onStateChange: (event) => {
              if (event.data === 1) {
                stop();
                timer.current = window.setInterval(report, REPORT_EVERY_MS);
              } else if (event.data === 2) {
                stop();
                report();
              } else if (event.data === 0) {
                stop();
                report();
                callbacks.current.onEnded?.();
              }
            },
          },
        });
      })
      .catch(() => {
        // Without the script the video still plays, just without saving the place.
        if (cancelled || !host.current) return;
        const frame = document.createElement("iframe");
        frame.src = `https://www.youtube-nocookie.com/embed/${videoId}?rel=0&start=${Math.floor(start)}`;
        frame.title = title;
        frame.allow = "encrypted-media; picture-in-picture";
        frame.allowFullscreen = true;
        frame.referrerPolicy = "strict-origin-when-cross-origin";
        host.current.replaceChildren(frame);
      });
    return () => {
      cancelled = true;
      stop();
      // Save the place before leaving.
      report();
      player.current?.destroy();
      player.current = null;
    };
    // The player is built once for each video; the start time only matters on the first load.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [videoId]);

  return <div ref={host} className="wo-video" aria-label={title} />;
});
