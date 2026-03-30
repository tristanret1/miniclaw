import { Graphics, Renderer, RenderTexture, Sprite } from "pixi.js";

/**
 * LayerCache — utilities to prerender static layers (Graphics) into textures.
 * This turns many vector draw calls into a single textured sprite at runtime.
 */
export class LayerCache {
  private renderer: Renderer;

  constructor(renderer: Renderer) {
    this.renderer = renderer;
  }

  /**
   * Render a Graphics (or any display object) to a Sprite backed by RenderTexture.
   * The source is not mutated; caller can remove/destroy it after calling.
   */
  toSprite(source: Graphics): Sprite {
    // Compute local bounds to size the render texture tightly
    const bounds = source.getLocalBounds();
    const rt = RenderTexture.create({
      width: Math.max(1, Math.ceil(bounds.width)),
      height: Math.max(1, Math.ceil(bounds.height)),
    });

    // Align draw so the sprite's origin (0,0) matches original container placement
    const prevX = source.x;
    const prevY = source.y;
    // Temporarily shift to start at (0,0) inside RT
    source.x -= bounds.x;
    source.y -= bounds.y;
    this.renderer.render({ container: source, target: rt });
    // Restore
    source.x = prevX;
    source.y = prevY;

    const sprite = new Sprite(rt);
    sprite.x = bounds.x;
    sprite.y = bounds.y;
    return sprite;
  }
}

