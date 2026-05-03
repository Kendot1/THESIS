import { GoogleGenerativeAI } from "@google/generative-ai";
import { NextResponse } from "next/server";

// Initialize the Gemini API client
const genAI = new GoogleGenerativeAI(process.env.GEMINI_API_KEY_REASONING || "");

// Switch to Edge Runtime to eliminate Next.js Dev Server 30s compilation delays
export const runtime = "edge";

export async function POST(req: Request) {
  try {
    const body = await req.json();
    const { productName, currentPrice, predictedPrice, newsContext } = body;

    if (!process.env.GEMINI_API_KEY_REASONING) {
      return NextResponse.json(
        { error: "GEMINI_API_KEY_REASONING is missing in environment variables." },
        { status: 500 }
      );
    }

    const isUp = predictedPrice >= currentPrice;
    const trend = isUp ? "upward" : "downward";
    const percentChange = Math.abs(((predictedPrice - currentPrice) / currentPrice) * 100).toFixed(1);

    const prompt = `
      You are an expert agricultural market analyst for the NCR region in the Philippines.
      Analyze the price trend for ${productName}.
      
      Data:
      - Current Price: ₱${currentPrice}
      - Predicted Price: ₱${predictedPrice}
      - Forecast Trend: ${trend} by ${percentChange}%
      
      Recent Market News Context:
      ${newsContext}
      
      Task:
      Write a concise 2-3 sentence market reasoning explaining WHY this price trend is happening. 
      Use the provided news context to back up the hybrid AI model's prediction. 
      Be professional, direct, and focus on supply, demand, or environmental factors mentioned in the news.
    `;

    // Use Gemini 2.5 Flash as requested
    const model = genAI.getGenerativeModel({ model: "gemini-2.5-flash" });

    const result = await model.generateContent(prompt);
    const response = await result.response;
    const text = response.text();

    return NextResponse.json({ reasoning: text });
  } catch (error) {
    console.error("Gemini API Error:", error);
    return NextResponse.json(
      { error: "Failed to generate market analysis." },
      { status: 500 }
    );
  }
}
