import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Lets Docker's file-watcher work reliably on some host OS/filesystem combos
    watch: {
      usePolling: true,
    },
  },
});
