// Minimal Tiled JSON types for our use
export interface TiledTileset {
  firstgid: number;
  image: string;
  imagewidth: number;
  imageheight: number;
  tilewidth: number;
  tileheight: number;
  columns: number;
  tilecount: number;
  name: string;
}

export interface TiledLayer {
  id: number;
  name: string;
  type: string; // "tilelayer" | "objectgroup" etc.
  width: number;
  height: number;
  data?: number[]; // CSV/array encoding assumed
  opacity?: number;
  visible?: boolean;
}

export interface TiledMap {
  width: number;
  height: number;
  tilewidth: number;
  tileheight: number;
  layers: TiledLayer[];
  tilesets: TiledTileset[];
}

