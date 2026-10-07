// Exact mirror of server/video_camera.py. Change both together; verify_motion_vocabulary checks agreement.
export const CANVAS = [1920, 1080] as const;
type Rect = { x: number; y: number; w: number; h: number };
type Cam = Rect & { cam_x: number; cam_y: number; cam_zoom: number };

export function fittedScale(s: Rect, aspect: readonly [number, number]) {
  return Math.min((s.w * CANVAS[0]) / aspect[0], (s.h * CANVAS[1]) / aspect[1]);
}

function axis(focus: number, box: number, content: number): [number, number] {
  if (content <= box) return [0, 1];
  const length = box / content;
  return [Math.min(1 - length, Math.max(0, focus - length / 2)), length];
}

export function visibleWindow(s: Cam, aspect: readonly [number, number]) {
  const scale = fittedScale(s, aspect) * s.cam_zoom;
  const [left, width] = axis(s.cam_x, s.w * CANVAS[0], aspect[0] * scale);
  const [top, height] = axis(s.cam_y, s.h * CANVAS[1], aspect[1] * scale);
  return { left, top, width, height, scale };
}

/** Pixel placement of the source inside its layer box (relative to the box's top-left). */
export function contentBox(s: Cam, aspect: readonly [number, number]) {
  const { left, top, scale } = visibleWindow(s, aspect);
  const boxW = s.w * CANVAS[0];
  const boxH = s.h * CANVAS[1];
  const width = aspect[0] * scale;
  const height = aspect[1] * scale;
  return {
    width,
    height,
    left: width <= boxW ? (boxW - width) / 2 : -left * width,
    top: height <= boxH ? (boxH - height) / 2 : -top * height,
  };
}

export function project(s: Cam, aspect: readonly [number, number], px: number, py: number) {
  const box = contentBox(s, aspect);
  return {
    x: (s.x * CANVAS[0] + box.left + px * box.width) / CANVAS[0],
    y: (s.y * CANVAS[1] + box.top + py * box.height) / CANVAS[1],
  };
}

export function drifted<T extends Rect>(
  rect: T,
  drift: { x: number; y: number; zoom: number },
  depth: number,
  seconds: number,
): T {
  const scale = 1 + drift.zoom * seconds * depth;
  return {
    ...rect,
    x: 0.5 + (rect.x - 0.5) * scale + drift.x * seconds * depth,
    y: 0.5 + (rect.y - 0.5) * scale + drift.y * seconds * depth,
    w: rect.w * scale,
    h: rect.h * scale,
  };
}
