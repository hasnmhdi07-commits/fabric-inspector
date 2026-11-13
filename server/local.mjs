// Run the API on this PC:  node server/local.mjs   -> http://127.0.0.1:3000/api/health
import { app } from "./app.mjs";
import { getEngine } from "./engine.mjs";

const port = Number(process.env.PORT) || 3000;
app.listen(port, "127.0.0.1", async () => {
  console.log(`Fabric Inspector API on http://127.0.0.1:${port}`);
  await getEngine();
  console.log("engine ready");
});
