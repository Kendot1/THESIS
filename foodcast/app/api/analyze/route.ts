import { GoogleGenerativeAI } from "@google/generative-ai";
import { NextResponse } from "next/server";

export const maxDuration = 60; // Allow more time for Gemini/Groq processing
export async function POST(req: Request) {
  try {
    const body = await req.json();
    const { productName, currentPrice, predictedPrice, newsContext, language } = body;

    const groqKey = process.env.GROQ_API_KEY_REASONING || process.env.GROQ_API_KEY;
    const geminiKey = process.env.GEMINI_API_KEY_REASONING;

    if (!groqKey && !geminiKey) {
      return NextResponse.json(
        { error: "Both GROQ_API_KEY_REASONING and GEMINI_API_KEY_REASONING are missing." },
        { status: 500 }
      );
    }

    const isUp = predictedPrice >= currentPrice;
    const trend = isUp ? "upward" : "downward";
    const percentChange = Math.abs(((predictedPrice - currentPrice) / currentPrice) * 100).toFixed(1);

    const languageInstruction = language === "tl" 
      ? `Write the reasoning entirely in natural, conversational Filipino (Tagalog). PAY SPECIAL ATTENTION TO PUNCTUATION: ensure proper use of commas, periods, and quotation marks where appropriate to make the sentences read clearly. Use the same level of detail, structure, and data as you would in English — include percentages, peso amounts, and specific factors. Just write it in Filipino instead of English. 
Example tone: "Ang inaasahang pagtaas ng presyo ng kamatis ay dulot ng mga malakas na pag-ulan at pagbaha sa Maguindanao na posibleng magdulot ng kakulangan sa supply. Bukod dito, ang pagtaas ng singil sa kuryente ng Meralco ngayong Hunyo ay maaaring magpataas ng gastos sa produksyon at transportasyon, na lalong magtutulak sa presyo pataas."`
      : "Write the reasoning entirely in English.";

    const systemPrompt = `You are an expert agricultural market analyst for the NCR region in the Philippines. Write a concise 2-3 sentence market reasoning explaining WHY the price trend for the specified product is happening based on the provided news context and data. Be professional, direct, and focus on supply, demand, or environmental factors mentioned in the news. Do NOT repeat the same point. Always finish your last sentence completely. ${languageInstruction}`;

    const userPrompt = `
      Product: ${productName}
      
      Data:
      - Current Price: ₱${currentPrice}
      - Predicted Price: ₱${predictedPrice}
      - Forecast Trend: ${trend} by ${percentChange}%
      
      Recent Market News Context:
      ${newsContext}
    `;

    // Attempt 1: Groq (Faster)
    if (groqKey) {
      try {
        const groqResponse = await fetch("https://api.groq.com/openai/v1/chat/completions", {
          method: "POST",
          headers: {
            "Authorization": `Bearer ${groqKey}`,
            "Content-Type": "application/json"
          },
          body: JSON.stringify({
            model: "openai/gpt-oss-120b",
            messages: [
              { role: "system", content: systemPrompt },
              { role: "user", content: userPrompt }
            ],
            temperature: 0.7,
            max_tokens: 350
          })
        });

        if (groqResponse.ok) {
          const data = await groqResponse.json();
          const reasoning = data.choices[0]?.message?.content?.trim() || "";
          if (reasoning) {
            return NextResponse.json({ reasoning });
          }
        } else {
          const errBody = await groqResponse.text();
          console.warn(`Groq request failed (${groqResponse.status}):`, errBody);
        }
      } catch (err) {
        console.warn("Groq network/parse error, falling back to Gemini:", err);
      }
    }

    // Attempt 2: Gemini (Fallback)
    if (geminiKey) {
      const genAI = new GoogleGenerativeAI(geminiKey);
      const model = genAI.getGenerativeModel({ model: "gemini-3.5-flash" });
      const prompt = `${systemPrompt}\n\n${userPrompt}`;
      
      const result = await model.generateContent(prompt);
      const response = await result.response;
      return NextResponse.json({ reasoning: response.text() });
    }

    throw new Error("Both AI providers failed.");
  } catch (error: any) {
    console.error("Analysis Error:", error);
    return NextResponse.json(
      { error: "Failed to generate market analysis.", details: error.message },
      { status: 500 }
    );
  }
}
