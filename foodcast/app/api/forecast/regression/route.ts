import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

export const runtime = 'nodejs';

interface Point {
  actual: number;
  predicted: number;
  date?: string;
  category?: string;
}

interface CommodityMetrics {
  name: string;
  variant: string;
  category: string;
  unit: string;
  count: number;
  mae_php: number;
  rmse_php: number;
  mape_pct: number;
  r_squared: number;
  slope: number;
  intercept: number;
  std_err: number;
  confidence_level_pct: number;
  empirical_coverage_pct: number;
  sample_points: Point[];
}

interface RegressionAnalysisData {
  overall: {
    count: number;
    mae_php: number;
    rmse_php: number;
    mape_pct: number;
    r_squared: number;
    slope: number;
    intercept: number;
    std_err: number;
    confidence_level_pct: number;
    empirical_coverage_pct: number;
    sample_points: Point[];
  };
  categories: Record<string, {
    count: number;
    mae_php: number;
    rmse_php: number;
    mape_pct: number;
    r_squared: number;
    slope: number;
    intercept: number;
    std_err: number;
    confidence_level_pct: number;
    empirical_coverage_pct: number;
  }>;
  commodities: CommodityMetrics[];
}

let cachedData: RegressionAnalysisData | null = null;

function loadRegressionData(): RegressionAnalysisData | null {
  if (cachedData) return cachedData;
  try {
    const filePath = path.join(process.cwd(), 'artifacts/accuracy/regression_analysis.json');
    if (fs.existsSync(filePath)) {
      const content = fs.readFileSync(filePath, 'utf-8');
      cachedData = JSON.parse(content) as RegressionAnalysisData;
      return cachedData;
    }
  } catch (err) {
    console.error('Failed to load regression_analysis.json:', err);
  }
  return null;
}

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const productName = searchParams.get('product')?.toLowerCase();
  const categoryName = searchParams.get('category')?.toLowerCase();

  const data = loadRegressionData();
  if (!data) {
    return NextResponse.json({ error: 'Regression analysis data not available' }, { status: 404 });
  }

  // If specific product requested
  if (productName) {
    const matched = data.commodities.find(c => 
      c.name.toLowerCase() === productName || 
      `${c.name} (${c.variant})`.toLowerCase() === productName ||
      c.name.toLowerCase().includes(productName)
    );

    if (matched) {
      return NextResponse.json({
        scope: 'commodity',
        product: matched.name,
        variant: matched.variant,
        category: matched.category,
        unit: matched.unit,
        metrics: {
          rmse_php: matched.rmse_php,
          mae_php: matched.mae_php,
          mape_pct: matched.mape_pct,
          r_squared: matched.r_squared,
          slope: matched.slope,
          intercept: matched.intercept,
          confidence_level_pct: matched.confidence_level_pct,
          empirical_coverage_pct: matched.empirical_coverage_pct,
          count: matched.count,
        },
        points: matched.sample_points,
      });
    }
  }

  // If specific category requested
  if (categoryName && data.categories[categoryName]) {
    const cat = data.categories[categoryName];
    return NextResponse.json({
      scope: 'category',
      category: categoryName,
      metrics: cat,
      points: data.overall.sample_points.filter(p => p.category?.toLowerCase() === categoryName),
    });
  }

  // Overall system return
  return NextResponse.json({
    scope: 'overall',
    metrics: {
      rmse_php: data.overall.rmse_php,
      mae_php: data.overall.mae_php,
      mape_pct: data.overall.mape_pct,
      r_squared: data.overall.r_squared,
      slope: data.overall.slope,
      intercept: data.overall.intercept,
      confidence_level_pct: data.overall.confidence_level_pct,
      empirical_coverage_pct: data.overall.empirical_coverage_pct,
      count: data.overall.count,
    },
    categories: Object.keys(data.categories),
    commodities: data.commodities.map(c => ({
      name: c.name,
      variant: c.variant,
      category: c.category,
      confidence_level_pct: c.confidence_level_pct,
      rmse_php: c.rmse_php,
      mae_php: c.mae_php,
      mape_pct: c.mape_pct,
    })),
    points: data.overall.sample_points,
  });
}
