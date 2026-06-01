"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Sparkles, RefreshCw } from "lucide-react";

export function AiNarrative({ outletId }: { outletId: string }) {
  const [loading, setLoading] = useState(false);
  const [text, setText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function explain() {
    setLoading(true);
    setError(null);
    try {
      const r = await api.explain(outletId);
      setText(r.narrative);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-3">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-primary" />
              AI explanation
            </CardTitle>
            <CardDescription>
              A Gemini-generated, business-friendly summary of why this outlet
              received its score and what the sales team should consider next.
            </CardDescription>
          </div>
          <Button onClick={explain} disabled={loading} size="sm">
            {loading ? (
              <RefreshCw className="h-4 w-4 animate-spin" />
            ) : text ? (
              "Regenerate"
            ) : (
              "Explain this outlet"
            )}
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {error && (
          <div className="rounded-md border border-danger/40 bg-danger/10 p-3 text-sm text-danger">
            {error}
          </div>
        )}
        {!text && !error && !loading && (
          <p className="text-sm text-muted-foreground">
            Click <em>Explain this outlet</em> to ask Gemini 2.5 Flash for a
            plain-English explanation grounded in the SHAP drivers, the
            counterfactuals, and the recommended actions for this outlet.
          </p>
        )}
        {loading && (
          <p className="text-sm text-muted-foreground">Generating…</p>
        )}
        {text && (
          <article className="prose prose-sm max-w-none whitespace-pre-wrap text-sm leading-relaxed">
            {text}
          </article>
        )}
      </CardContent>
    </Card>
  );
}
