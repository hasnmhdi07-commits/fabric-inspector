// Live camera inside the page (getUserMedia). If the browser has no camera access, the caller falls back to
// the system camera through <input capture>.
export class Camera {
  constructor(video) { this.video = video; this.stream = null; this.facing = "environment"; this.torchOn = false; }

  static get supported() { return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia); }
  get active() { return !!this.stream; }

  async start() {
    this.stop();
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: { facingMode: { ideal: this.facing }, width: { ideal: 2560 }, height: { ideal: 1440 } },
    });
    this.video.srcObject = this.stream;
    await this.video.play();
    this.torchOn = false;
  }

  stop() {
    if (this.stream) for (const t of this.stream.getTracks()) t.stop();
    this.stream = null; this.video.srcObject = null;
  }

  async flip() { this.facing = this.facing === "environment" ? "user" : "environment"; await this.start(); }

  get hasTorch() {
    const t = this.stream && this.stream.getVideoTracks()[0];
    return !!(t && t.getCapabilities && t.getCapabilities().torch);
  }
  async toggleTorch() {
    this.torchOn = !this.torchOn;
    await this.stream.getVideoTracks()[0].applyConstraints({ advanced: [{ torch: this.torchOn }] });
    return this.torchOn;
  }

  /** The current frame at the camera's full resolution, as a JPEG blob. */
  capture() {
    const v = this.video, cv = document.createElement("canvas");
    cv.width = v.videoWidth; cv.height = v.videoHeight;
    if (!cv.width || !cv.height) return Promise.reject(new Error("The camera is not ready yet."));
    cv.getContext("2d").drawImage(v, 0, 0);
    return new Promise((res, rej) => cv.toBlob((b) => (b ? res(b) : rej(new Error("Could not read the camera frame."))), "image/jpeg", 0.95));
  }
}
