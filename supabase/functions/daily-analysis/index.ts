// Supabase Edge Function: Trigger daily analysis
// Runs via Supabase cron job

import { serve } from "https://deno.land/std@0.168.0/http/server.ts";

serve(async (req) => {
  const { symbol } = await req.json().catch(() => ({}));

  // Call the Railway API to run analysis
  const API_URL = Deno.env.get("RAILWAY_API_URL") || "https://your-railway-app.up.railway.app";

  try {
    const response = await fetch(`${API_URL}/analyze-index`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });

    const data = await response.json();

    return new Response(
      JSON.stringify({ 
        success: true, 
        analyzed: data.length,
        timestamp: new Date().toISOString()
      }),
      { headers: { "Content-Type": "application/json" } }
    );
  } catch (error) {
    return new Response(
      JSON.stringify({ success: false, error: error.message }),
      { status: 500, headers: { "Content-Type": "application/json" } }
    );
  }
});
