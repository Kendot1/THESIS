import { NextResponse } from "next/server";
import { supabase } from "@/lib/supabase";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id: productId } = await params;
    
    if (!productId) {
      return NextResponse.json(
        { error: "Product ID is required" },
        { status: 400 }
      );
    }

    // Get today's date in YYYY-MM-DD format based on UTC
    const today = new Date().toISOString().split('T')[0];

    // Call the Supabase RPC to securely increment the view count
    const { error } = await supabase.rpc('increment_product_view', {
      p_id: productId,
      p_date: today
    });

    if (error) {
      console.error("Failed to increment view:", error);
      return NextResponse.json(
        { error: "Failed to increment view count" },
        { status: 500 }
      );
    }

    return NextResponse.json({ success: true });
  } catch (err) {
    console.error("Error in interact API:", err);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}
