import { createReadStream, existsSync } from "node:fs";
import { stat } from "node:fs/promises";
import { createServer } from "node:http";
import { extname, join, normalize } from "node:path";

const DIST_DIR = join(process.cwd(), "dist");
const PORT = Number.parseInt(process.env.PORT ?? "3000", 10);

const CONTENT_TYPES = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".ico": "image/x-icon",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".map": "application/json; charset=utf-8",
  ".png": "image/png",
  ".svg": "image/svg+xml; charset=utf-8",
  ".txt": "text/plain; charset=utf-8",
  ".webp": "image/webp",
};

function resolveAssetPath(urlPath) {
  const decodedPath = decodeURIComponent(urlPath.split("?")[0]);
  const normalizedPath = normalize(decodedPath).replace(/^(\.\.[/\\])+/, "");
  const relativePath = normalizedPath === "/" ? "index.html" : normalizedPath.replace(/^[/\\]/, "");

  return join(DIST_DIR, relativePath);
}

function sendFile(response, filePath) {
  const extension = extname(filePath);
  response.writeHead(200, {
    "Content-Type": CONTENT_TYPES[extension] ?? "application/octet-stream",
    "Cache-Control": extension === ".html" ? "no-cache" : "public, max-age=31536000, immutable",
  });

  createReadStream(filePath).pipe(response);
}

const server = createServer(async (request, response) => {
  if (!request.url) {
    response.writeHead(400);
    response.end("Bad Request");
    return;
  }

  if (request.url === "/health") {
    response.writeHead(200, { "Content-Type": "text/plain; charset=utf-8" });
    response.end("ok");
    return;
  }

  const assetPath = resolveAssetPath(request.url);

  try {
    const assetStats = await stat(assetPath);
    if (assetStats.isFile()) {
      sendFile(response, assetPath);
      return;
    }
  } catch {
    // Fall back to the SPA entrypoint when the asset is not found.
  }

  const indexPath = join(DIST_DIR, "index.html");
  if (!existsSync(indexPath)) {
    response.writeHead(500, { "Content-Type": "text/plain; charset=utf-8" });
    response.end("dist/index.html not found");
    return;
  }

  sendFile(response, indexPath);
});

server.listen(PORT, "0.0.0.0", () => {
  console.log(`Frontend server listening on http://0.0.0.0:${PORT}`);
});
