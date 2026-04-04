"use client";
import {
  Brain,
  Database,
  BarChart3,
  Cpu,
  LineChart,
  Shield,
  Users,
  TrendingUp,
  Layers,
  Target,
} from "lucide-react";
import Header from "../components/Header";
import Footer from "../components/Footer";
import WaveDivider from "../components/WaveDivider";
import ScrollReveal from "../components/ScrollReveal";

const methodologySteps = [
  {
    step: 1,
    icon: <Database className="w-6 h-6" />,
    title: "Data Collection",
    description:
      "Gathering historical price data from NCR markets including daily prices, supply volumes, weather patterns, and seasonal trends across multiple commodities.",
  },
  {
    step: 2,
    icon: <Layers className="w-6 h-6" />,
    title: "Data Preprocessing",
    description:
      "Cleaning, normalizing, and structuring raw market data. Handling missing values, outlier detection, and feature engineering to prepare the dataset for model training.",
  },
  {
    step: 3,
    icon: <Cpu className="w-6 h-6" />,
    title: "Model Training",
    description:
      "Training machine learning algorithms including LSTM neural networks, ARIMA models, and ensemble methods on historical data to learn price patterns and correlations.",
  },
  {
    step: 4,
    icon: <Target className="w-6 h-6" />,
    title: "Validation & Testing",
    description:
      "Rigorous cross-validation and backtesting against holdout data to ensure prediction accuracy and model reliability across different market conditions.",
  },
  {
    step: 5,
    icon: <LineChart className="w-6 h-6" />,
    title: "Price Forecasting",
    description:
      "Generating future price predictions with confidence intervals, trend analysis, and market sentiment indicators for each tracked product.",
  },
  {
    step: 6,
    icon: <Shield className="w-6 h-6" />,
    title: "Continuous Monitoring",
    description:
      "Real-time model performance monitoring, automatic retraining when needed, and drift detection to maintain forecast accuracy over time.",
  },
];

const stats = [
  { value: "50+", label: "Products Tracked", icon: <BarChart3 className="w-5 h-5" /> },
  { value: "98.5%", label: "Model Accuracy", icon: <Target className="w-5 h-5" /> },
  { value: "10K+", label: "Data Points Analyzed", icon: <Database className="w-5 h-5" /> },
  { value: "24/7", label: "Real-time Updates", icon: <TrendingUp className="w-5 h-5" /> },
];

export default function AboutPage() {
  return (
    <>
      <Header />
      <main id="main-content" className="pt-20">
        {/* ─── Hero ──────────────────────────────────── */}
        <section className="relative bg-gradient-to-br from-primary-800 via-primary-800 to-primary-900 py-20 sm:py-28 overflow-hidden">
          <div className="absolute inset-0 pointer-events-none" aria-hidden="true">
            <div className="absolute top-20 right-[20%] w-[500px] h-[500px] bg-accent/6 rounded-full blur-[120px]" />
            <div className="absolute bottom-0 left-[10%] w-[350px] h-[350px] bg-orange/5 rounded-full blur-[90px]" />
          </div>

          <div className="relative max-w-7xl mx-auto px-5 lg:px-10">
            <div className="max-w-3xl">
              <div className="inline-flex items-center gap-2 px-4 py-1.5 bg-accent/10 border border-accent/20 rounded-full mb-8">
                <Brain className="w-4 h-4 text-accent" />
                <span className="text-accent text-xs font-medium tracking-wide">
                  About the Project
                </span>
              </div>

              <h1
                className="text-3xl sm:text-4xl lg:text-5xl xl:text-6xl font-bold text-white leading-[1.1] mb-6"
                style={{ fontFamily: "var(--font-display)" }}
              >
                What is{" "}
                <span className="text-transparent bg-clip-text bg-gradient-to-r from-accent to-accent-light">
                  FOODCAST
                </span>
                ?
              </h1>

              <p className="text-white/55 text-lg sm:text-xl leading-relaxed max-w-2xl">
                FOODCAST is an AI-Based Forecasting and Market Analysis system
                for Agri-Fishery Food Prices in NCR (National Capital Region)
                Markets. It leverages advanced machine learning algorithms to
                predict future price movements and provide actionable market
                intelligence.
              </p>
            </div>
          </div>
        </section>

        <WaveDivider from="#0B3D2E" to="#FDFBF7" />

        {/* ─── Mission / Overview ──────────────────────── */}
        <section className="py-16 sm:py-20 bg-surface" aria-labelledby="mission-heading">
          <div className="max-w-7xl mx-auto px-5 lg:px-10">
            <div className="grid lg:grid-cols-2 gap-12 lg:gap-16 items-center">
              <ScrollReveal animation="slide-left">
                <div>
                  <h2
                    id="mission-heading"
                    className="text-2xl sm:text-3xl font-bold text-gray-900 mb-5"
                    style={{ fontFamily: "var(--font-display)" }}
                  >
                    Empowering Smarter
                    <br />
                    <span className="text-transparent bg-clip-text bg-gradient-to-r from-primary-800 to-primary-600">
                      Market Decisions
                    </span>
                  </h2>
                  <div className="space-y-4 text-gray-600 leading-relaxed">
                    <p>
                      The food supply chain in the Philippines, particularly in
                      NCR markets, faces significant challenges with price
                      volatility affecting both consumers and producers.
                    </p>
                    <p>
                      FOODCAST addresses this by providing AI-powered price
                      forecasting that helps stakeholders — from market vendors
                      and buyers to researchers and policymakers — anticipate
                      price changes and make informed decisions.
                    </p>
                    <p>
                      Our system uses a combination of historical price data,
                      seasonal patterns, supply-demand indicators, and advanced
                      algorithms to generate accurate forecasts.
                    </p>
                  </div>
                </div>
              </ScrollReveal>

              <ScrollReveal animation="slide-right" delay={200}>
                <div className="grid grid-cols-2 gap-4">
                  {stats.map((stat, i) => (
                    <div
                      key={stat.label}
                      className="bg-white rounded-2xl border border-gray-100 p-6 shadow-sm hover:shadow-md transition-all duration-300 hover:-translate-y-0.5"
                    >
                      <div className="w-10 h-10 rounded-xl bg-accent/10 flex items-center justify-center text-accent mb-4">
                        {stat.icon}
                      </div>
                      <div className="text-2xl sm:text-3xl font-bold text-primary-800 mb-1">
                        {stat.value}
                      </div>
                      <div className="text-xs text-gray-500 font-medium">
                        {stat.label}
                      </div>
                    </div>
                  ))}
                </div>
              </ScrollReveal>
            </div>
          </div>
        </section>

        {/* ─── Methodology ─────────────────────────────── */}
        <div className="bg-surface">
          <WaveDivider from="#FDFBF7" to="#0B3D2E" />
        </div>

        <section
          className="relative py-20 sm:py-28 bg-primary-800 overflow-hidden"
          aria-labelledby="methodology-heading"
        >
          <div className="absolute inset-0 pointer-events-none" aria-hidden="true">
            <div className="absolute -top-32 right-0 w-[600px] h-[600px] bg-accent/4 rounded-full blur-[150px]" />
            <div className="absolute -bottom-32 left-0 w-[400px] h-[400px] bg-accent/3 rounded-full blur-[120px]" />
          </div>

          <div className="relative max-w-7xl mx-auto px-5 lg:px-10">
            <ScrollReveal>
              <div className="text-center mb-16">
                <h2
                  id="methodology-heading"
                  className="text-3xl sm:text-4xl lg:text-5xl font-bold text-white mb-5"
                  style={{ fontFamily: "var(--font-display)" }}
                >
                  Our{" "}
                  <span className="text-transparent bg-clip-text bg-gradient-to-r from-accent to-accent-light">
                    Methodology
                  </span>
                </h2>
                <p className="text-white/50 max-w-2xl mx-auto text-base sm:text-lg">
                  A systematic, data-driven approach to food price forecasting
                  using state-of-the-art AI techniques
                </p>
              </div>
            </ScrollReveal>

            {/* Vertical Timeline */}
            <div className="relative max-w-3xl mx-auto">
              {/* Timeline line */}
              <div
                className="absolute left-6 sm:left-8 top-0 bottom-0 w-px bg-gradient-to-b from-accent/40 via-accent/20 to-transparent"
                aria-hidden="true"
              />

              <div className="space-y-10">
                {methodologySteps.map((step, i) => (
                  <ScrollReveal
                    key={step.step}
                    delay={i * 120}
                    animation="fade-up"
                  >
                    <div className="relative flex gap-6 sm:gap-8">
                      {/* Timeline node */}
                      <div className="relative z-10 shrink-0">
                        <div className="w-12 h-12 sm:w-16 sm:h-16 rounded-2xl bg-accent/10 border border-accent/20 flex items-center justify-center text-accent
                          shadow-[0_0_20px_rgba(126,217,87,0.1)] transition-all duration-300 hover:bg-accent/20 hover:scale-105">
                          {step.icon}
                        </div>
                      </div>

                      {/* Content */}
                      <div className="flex-1 pb-2">
                        <div className="flex items-center gap-3 mb-2">
                          <span className="text-xs font-semibold text-accent/60 uppercase tracking-widest">
                            Step {step.step}
                          </span>
                        </div>
                        <h3
                          className="text-lg sm:text-xl font-bold text-white mb-2"
                          style={{ fontFamily: "var(--font-display)" }}
                        >
                          {step.title}
                        </h3>
                        <p className="text-white/45 text-sm sm:text-base leading-relaxed">
                          {step.description}
                        </p>
                      </div>
                    </div>
                  </ScrollReveal>
                ))}
              </div>
            </div>
          </div>
        </section>

        <WaveDivider from="#0B3D2E" to="#FDFBF7" />

        {/* ─── Team / Attribution ──────────────────────── */}
        <section className="py-16 sm:py-20 bg-surface" aria-labelledby="team-heading">
          <div className="max-w-7xl mx-auto px-5 lg:px-10">
            <ScrollReveal>
              <div className="text-center mb-12">
                <h2
                  id="team-heading"
                  className="text-2xl sm:text-3xl font-bold text-gray-900 mb-4"
                  style={{ fontFamily: "var(--font-display)" }}
                >
                  Built for the Filipino Market
                </h2>
                <p className="text-gray-500 max-w-xl mx-auto">
                  FOODCAST is a thesis project designed to support smarter food
                  market decisions through technology and data science.
                </p>
              </div>
            </ScrollReveal>

            <ScrollReveal animation="scale-in" delay={200}>
              <div className="grid sm:grid-cols-3 gap-6 max-w-3xl mx-auto">
                {[
                  {
                    icon: <Users className="w-6 h-6" />,
                    title: "Research-Backed",
                    description:
                      "Built on rigorous academic research and real-world market data from NCR.",
                  },
                  {
                    icon: <Brain className="w-6 h-6" />,
                    title: "AI-Powered",
                    description:
                      "Utilizes advanced ML algorithms for high-accuracy price prediction.",
                  },
                  {
                    icon: <Shield className="w-6 h-6" />,
                    title: "Open & Transparent",
                    description:
                      "Clear methodology. Reproducible results. Trustworthy forecasts.",
                  },
                ].map((item) => (
                  <div
                    key={item.title}
                    className="bg-white rounded-2xl border border-gray-100 p-6 text-center shadow-sm hover:shadow-md transition-all duration-300 hover:-translate-y-0.5"
                  >
                    <div className="w-12 h-12 rounded-xl bg-primary-50 flex items-center justify-center text-primary-800 mx-auto mb-4">
                      {item.icon}
                    </div>
                    <h3 className="font-semibold text-gray-900 mb-2 text-sm">
                      {item.title}
                    </h3>
                    <p className="text-gray-500 text-xs leading-relaxed">
                      {item.description}
                    </p>
                  </div>
                ))}
              </div>
            </ScrollReveal>
          </div>
        </section>
      </main>
      <Footer />
    </>
  );
}
