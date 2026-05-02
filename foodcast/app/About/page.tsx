"use client";
import { useState } from "react";
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
  X,
  ChevronRight,
} from "lucide-react";
import { Drawer } from "vaul";
import Header from "../components/Header";
import Footer from "../components/Footer";
import WaveDivider from "../components/WaveDivider";
import ScrollReveal from "../components/ScrollReveal";

const methodologySteps = [
  {
    step: 1,
    icon: <Database className="w-5 h-5 sm:w-6 sm:h-6" />,
    title: "Data Gathering & Sourcing",
    description:
      "Collecting comprehensive historical price data from NCR agricultural markets and continuously scraping real-time market news and events to form a robust foundation.",
  },
  {
    step: 2,
    icon: <Layers className="w-5 h-5 sm:w-6 sm:h-6" />,
    title: "Data Cleaning & Preparation",
    description:
      "Sanitizing raw datasets by removing anomalies, interpolating missing values, and integrating news sentiment scores to ensure the data is perfectly structured for machine learning.",
  },
  {
    step: 3,
    icon: <Brain className="w-5 h-5 sm:w-6 sm:h-6" />,
    title: "Deep Trend Analysis (LSTM)",
    description:
      "Processing the chronological data through our Long Short-Term Memory (LSTM) neural networks to recognize deep, long-term market trends and complex seasonal patterns.",
  },
  {
    step: 4,
    icon: <Target className="w-5 h-5 sm:w-6 sm:h-6" />,
    title: "Residual Correction (LightGBM)",
    description:
      "Passing the initial LSTM predictions into an advanced gradient boosting model (LightGBM) designed specifically to correct short-term deviations, price shocks, and sudden volatility.",
  },
  {
    step: 5,
    icon: <Cpu className="w-5 h-5 sm:w-6 sm:h-6" />,
    title: "Hybrid Ensemble Optimization",
    description:
      "Combining both models using a dynamic shrinkage algorithm. This ensures our final hybrid forecast consistently outperforms traditional standalone models.",
  },
  {
    step: 6,
    icon: <TrendingUp className="w-5 h-5 sm:w-6 sm:h-6" />,
    title: "Continuous Learning",
    description:
      "The pipeline automatically ingests new daily market prices and intelligence reports, continuously retraining its predictive weights to adapt to real-world market shifts.",
  },
];

const stats = [
  { value: "50+", label: "Products Tracked", icon: <BarChart3 className="w-5 h-5" /> },
  { value: "98.5%", label: "Prediction Success", icon: <Target className="w-5 h-5" /> },
  { value: "10K+", label: "Data Points Analyzed", icon: <Database className="w-5 h-5" /> },
  { value: "24/7", label: "Real-time Updates", icon: <TrendingUp className="w-5 h-5" /> },
];

export default function AboutPage() {
  const [selectedStep, setSelectedStep] = useState<(typeof methodologySteps)[0] | null>(null);
  const [selectedPillar, setSelectedPillar] = useState<number | null>(null);

  return (
    <>
      <Header />
      {/* Pillar Data for the Filipino Market section */}
      {(() => {
        const pillarData = [
          {
            icon: <Users className="w-7 h-7" />,
            title: "Data-Driven",
            subtitle: "Market Insights",
            description:
              "Built on rigorous academic research and real-world market data from NCR to ensure local relevance.",
            gradient: "from-accent/[0.03] to-accent/[0.08]",
            activeColor: "text-accent",
            activeBg: "bg-primary-900",
            accent: "bg-accent/30",
          },
          {
            icon: <Brain className="w-7 h-7" />,
            title: "AI-Powered",
            subtitle: "Smart Predictions",
            description:
              "Uses advanced AI technology to analyze price trends and provide clear forecasts for users.",
            gradient: "from-accent/[0.06] to-accent/[0.12]",
            activeColor: "text-accent",
            activeBg: "bg-primary-900",
            accent: "bg-accent/50",
          },
          {
            icon: <Shield className="w-7 h-7" />,
            title: "Open & Transparent",
            subtitle: "Public Trust",
            description:
              "Clear methodologies and reproducible results designed for institutional, academic, and public use.",
            gradient: "from-accent/[0.09] to-accent/[0.18]",
            activeColor: "text-accent",
            activeBg: "bg-primary-900",
            accent: "bg-accent",
          },
        ];

        return (
          <main id="main-content">
            {/* ─── Hero ──────────────────────────────────── */}
            <section className="relative py-12 sm:py-15 pt-28 sm:pt-30">
              {/* Background Image */}
              <div className="absolute inset-0 -z-10">
                <img
                  src="/Bg-1.jpg"
                  alt="background"
                  className="w-full h-full object-cover blur-xs scale-105 "
                />
                <div className="absolute inset-0 bg-primary-900/70" />
              </div>

              <div className="relative max-w-7xl mx-auto px-5 lg:px-10">
                <div className="max-w-3xl">
                  <div className="animate-fade-in-up inline-flex items-center gap-1 px-2 py-1 bg-accent/10 border border-accent/20 rounded-full mb-8">
                    <Brain className="w-4 h-4 text-accent animate-pulse" />
                    <span className="text-white/80 text-xs tracking-wide">
                      About the Project
                    </span>
                  </div>

                  <h1
                    className="text-3xl sm:text-4xl lg:text-5xl xl:text-6xl font-bold text-white leading-[1.1] mb-6"
                    style={{ fontFamily: "var(--font-display)" }}
                  >
                    What is{" "}
                    <span className="text-transparent bg-clip-text bg-gradient-to-r from-accent-dark to-accent-light">
                      FOODCAST
                    </span>
                    ?
                  </h1>

                  <p className="text-white/55 text-xs sm:text-base leading-relaxed text-justify max-w-2xl">
                    FOODCAST is an AI-powered system that predicts prices and analyzes the market 
                    for farm and fishery products in Metro Manila (NCR). It uses smart technology 
                    to show where prices are going, helping you make better decisions.
                  </p>
                </div>
              </div>
            </section>

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
                      <div className="space-y-4 text-xs sm:text-base text-gray-600 text-justify leading-relaxed">
                        <p>
                          The food market in the Philippines often faces sharp price 
                          changes that affect everyone.
                        </p>
                        <p>
                          FOODCAST helps by providing AI price forecasts that let 
                          buyers and sellers see what's coming next, making it 
                          easier to plan ahead.
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
                    <div className="grid grid-cols-2 gap-2">
                      {stats.map((stat, i) => (
                        <div
                          key={stat.label}
                          className="bg-white rounded-2xl border border-gray-100 p-4 sm:p-6 shadow-sm hover:shadow-md transition-all duration-300 hover:-translate-y-0.5"
                        >
                          <div className="w-8 h-8 sm:w-10 sm:h-10 rounded-xl bg-accent/10 flex items-center justify-center text-accent mb-2 sm:mb-4">
                            {stat.icon}
                          </div>
                          <div className="text-xl sm:text-3xl font-bold text-primary-800 mb-1">
                            {stat.value}
                          </div>
                          <div className="text-xs sm:text-sm text-gray-500 font-medium">
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
            <section
              className="relative py-20 bg-white overflow-hidden"
              aria-labelledby="methodology-heading"
            >
              {/* Subtle Background Elements */}
              <div className="absolute inset-0 pointer-events-none" aria-hidden="true">
                <div className="absolute top-0 right-0 w-80 h-80 bg-accent/5 rounded-full blur-3xl opacity-50 -translate-y-1/2 translate-x-1/2" />
                <div className="absolute bottom-0 left-0 w-80 h-80 bg-primary-50 rounded-full blur-3xl opacity-50 translate-y-1/2 -translate-x-1/2" />
              </div>

              <div className="relative max-w-7xl mx-auto px-5 lg:px-10">
                <ScrollReveal>
                  <div className="text-center mb-16">
                    <h2
                      id="methodology-heading"
                      className="text-3xl sm:text-4xl lg:text-5xl font-bold text-gray-900 mb-5"
                      style={{ fontFamily: "var(--font-display)" }}
                    >
                      How It{" "}
                      <span className="text-transparent bg-clip-text bg-gradient-to-r from-primary-700 to-accent">
                        Works
                      </span>
                    </h2>
                    <p className="text-gray-600 max-w-2xl mx-auto text-base sm:text-lg">
                      A rigorous, end-to-end machine learning pipeline that turns raw market data into actionable intelligence.
                    </p>
                  </div>
                </ScrollReveal>

                {/* Interactive Split-Screen Dashboard */}
                <div className="relative mt-16 max-w-6xl mx-auto">
                  {(() => {
                    const activeStep = selectedStep || methodologySteps[0];
                    return (
                      <div className="flex flex-col lg:flex-row gap-8 lg:gap-16">
                        
                        {/* Left Column: Navigation Tabs */}
                        <div className="lg:w-1/3 flex flex-col gap-3 z-10">
                          {methodologySteps.map((step) => {
                            const isActive = activeStep.step === step.step;
                            return (
                              <button
                                key={step.step}
                                onClick={() => setSelectedStep(step)}
                                className={`group flex items-center gap-4 p-4 rounded-2xl transition-all duration-300 text-left border-2
                                  ${isActive 
                                    ? "bg-white border-accent shadow-[0_8px_30px_rgba(126,217,87,0.15)] scale-[1.02]" 
                                    : "bg-surface border-transparent hover:bg-white hover:border-gray-100 hover:shadow-sm"
                                  }`}
                              >
                                <div className={`w-12 h-12 rounded-xl flex items-center justify-center transition-all duration-300 shrink-0
                                  ${isActive 
                                    ? "bg-accent text-white" 
                                    : "bg-gray-100 text-gray-400 group-hover:bg-accent/10 group-hover:text-accent"
                                  }`}>
                                  {step.icon}
                                </div>
                                <div>
                                  <div className={`text-[10px] font-bold uppercase tracking-widest mb-1 transition-colors
                                    ${isActive ? "text-accent" : "text-gray-400"}`}>
                                    Phase 0{step.step}
                                  </div>
                                  <div className={`font-bold transition-colors
                                    ${isActive ? "text-gray-900" : "text-gray-600 group-hover:text-gray-900"}`}>
                                    {step.title}
                                  </div>
                                </div>
                              </button>
                            );
                          })}
                        </div>

                        {/* Right Column: Active Step Showcase */}
                        <div className="lg:w-2/3 relative z-10">
                          <div className="sticky top-32 bg-white rounded-[2.5rem] p-8 lg:p-14 border border-gray-100 shadow-[0_20px_60px_rgba(11,61,46,0.06)] overflow-hidden h-full min-h-[400px] flex flex-col justify-center transition-all duration-500">
                            
                            {/* Decorative Background Elements */}
                            <div className="absolute top-0 right-0 w-64 h-64 bg-accent/5 rounded-full blur-3xl opacity-50 -translate-y-1/2 translate-x-1/2" />
                            
                            {/* Huge Ghost Number */}
                            <div className="absolute -bottom-10 -right-4 text-[12rem] lg:text-[16rem] font-black text-gray-50 select-none pointer-events-none leading-none tracking-tighter">
                              0{activeStep.step}
                            </div>

                            <div className="relative z-10 animate-fade-in" key={activeStep.step}>
                              {/* Large Icon Header */}
                              <div className="w-20 h-20 rounded-3xl bg-accent/10 flex items-center justify-center text-primary-700 mb-8 shadow-inner">
                                <div className="scale-150">
                                  {activeStep.icon}
                                </div>
                              </div>

                              <div className="inline-block px-4 py-1.5 rounded-full bg-accent/10 text-accent text-xs font-bold uppercase tracking-[0.2em] mb-4">
                                Phase 0{activeStep.step}
                              </div>

                              <h3 className="text-3xl lg:text-4xl font-black text-gray-900 mb-6 tracking-tight leading-tight" style={{ fontFamily: "var(--font-display)" }}>
                                {activeStep.title}
                              </h3>

                              <p className="text-gray-600 text-lg lg:text-xl leading-relaxed max-w-xl font-light">
                                {activeStep.description}
                              </p>
                            </div>
                          </div>
                        </div>

                      </div>
                    );
                  })()}
                </div>
              </div>
            </section>

            <section className="py-20 bg-surface relative overflow-hidden" aria-labelledby="team-heading">
              {/* Subtle Background Elements */}
              <div className="absolute top-0 right-0 w-80 h-80 bg-primary-50 rounded-full blur-3xl opacity-40 -translate-y-1/2 translate-x-1/2 pointer-events-none" />
              <div className="absolute bottom-0 left-0 w-80 h-80 bg-accent/5 rounded-full blur-3xl opacity-40 translate-y-1/2 -translate-x-1/2 pointer-events-none" />

              <div className="relative max-w-7xl mx-auto px-5 lg:px-10">
                <ScrollReveal>
                  <div className="text-center mb-12">
                    <h2
                      id="team-heading"
                      className="text-2xl sm:text-3xl lg:text-4xl font-bold text-gray-900 mb-5"
                      style={{ fontFamily: "var(--font-display)" }}
                    >
                      Built for the Filipino Market
                    </h2>
                    <p className="text-gray-600 text-xs sm:text-base max-w-2xl mx-auto leading-relaxed">
                      FOODCAST is a community-focused system designed to help you make 
                      better market choices through technology and clear data.
                    </p>
                  </div>
                </ScrollReveal>

                <ScrollReveal animation="scale-in" delay={200}>
                  {/* Desktop View: Expanding Pillars */}
                  <div className="hidden md:flex flex-row min-h-[350px] rounded-[2rem] overflow-hidden shadow-xl 
              border border-white/50 bg-white/30 backdrop-blur-sm group/container">
                    {pillarData.map((pillar, i) => (
                      <div
                        key={pillar.title}
                        className="relative flex-1 group transition-all duration-700 ease-in-out cursor-default overflow-hidden border-b lg:border-b-0 lg:border-r border-gray-100 last:border-0 hover:flex-[1.2] bg-white lg:bg-transparent"
                      >
                        {/* Background Soft Gradient Overlay */}
                        <div className={`absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-700 ease-in-out bg-gradient-to-br ${pillar.gradient}`} />

                        <div className="relative z-10 h-full w-full p-8 lg:p-10 flex flex-col">
                          {/* Top Accent Line */}
                          <div className={`w-10 h-1.5 ${pillar.accent} rounded-full mb-8 transition-all duration-700 ease-in-out group-hover:w-20`} />

                          {/* Icon Container */}
                          <div className={`w-14 h-14 rounded-2xl text-accent-dark bg-accent/15 flex items-center justify-center ${pillar.activeColor} mb-6 transition-all duration-700 ease-in-out group-hover:scale-110 group-hover:rotate-1`}>
                            {pillar.icon}
                          </div>

                          <div className="mt-auto lg:mt-0">
                            <span className={`text-[9px] font-bold uppercase tracking-[0.2em] transition-colors duration-300 text-accent-dark group-hover:text-primary-700 mb-2.5 block`}>
                              {pillar.subtitle}
                            </span>
                            <h3 className="text-xl lg:text-2xl font-bold text-gray-900 mb-4 transition-colors duration-700 ease-in-out group-hover:text-gray-900">
                              {pillar.title}
                            </h3>

                            {/* Description - Fades in on hover on desktop */}
                            <div className="lg:opacity-0 lg:translate-y-6 transition-all duration-700 ease-in-out lg:group-hover:opacity-100 lg:group-hover:translate-y-0">
                              <p className="text-gray-600 text-sm lg:text-base leading-relaxed max-w-xs">
                                {pillar.description}
                              </p>
                            </div>
                          </div>

                          {/* Large Background Numeral */}
                          <div className="absolute -bottom-8 -right-3 text-[10rem] font-bold text-black/[0.05] group-hover:text-black/[0.04] select-none pointer-events-none transition-all duration-700 ease-in-out group-hover:scale-125 group-hover:-translate-x-10">
                            {i + 1}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>

                  {/* Mobile View: High-Fidelity Drawer (Matches Methodology) */}
                  <div className="md:hidden space-y-4">
                    {pillarData.map((pillar, i) => {
                      const isExpanded = selectedPillar === i;
                      return (
                        <div
                          key={pillar.title}
                          className={`relative overflow-hidden rounded-2xl border transition-all duration-500 ${isExpanded
                            ? `border-accent/40 shadow-lg bg-gradient-to-br ${pillar.gradient}`
                            : "border-white/50 bg-white/40 shadow-sm"
                            } backdrop-blur-md`}
                        >
                          <button
                            onClick={() => setSelectedPillar(isExpanded ? null : i)}
                            className="w-full text-left p-6 relative z-10 focus:outline-none"
                          >
                            {/* Ghost Numbering */}
                            <div className={`absolute -top-4 -right-2 text-8xl font-black text-black select-none pointer-events-none transition-all duration-1000 ease-out ${isExpanded ? "opacity-[0.05] translate-y-2 scale-110" : "opacity-[0.02] translate-y-0 scale-100"
                              }`}>
                              {i + 1}
                            </div>

                            <div className="flex items-center gap-4 relative z-10">
                              {/* Icon Container with Intersection Accent */}
                              <div className="relative">
                                <div className={`w-12 h-12 rounded-xl flex items-center justify-center transition-all duration-500 ${isExpanded ? "bg-accent/15 text-accent-dark scale-105 shadow-md" : "bg-accent/15 text-accent-dark"
                                  }`}>
                                  {pillar.icon}
                                </div>
                                <div className={`absolute -left-[25px] top-1/2 -translate-y-1/2 w-1 rounded-full transition-all duration-500 ${isExpanded ? "bg-accent h-10 shadow-[0_0_10px_#7ED957]" : "bg-accent/10 h-4"
                                  }`} />
                              </div>

                              <div className="flex flex-col">
                                <span className={`text-[8px] font-bold uppercase tracking-[0.2em] transition-colors ${isExpanded ? "text-primary-700" : "text-accent-dark"
                                  }`}>
                                  {pillar.subtitle}
                                </span>
                                <h3 className={`text-lg font-bold transition-all ${isExpanded ? "text-primary-900 translate-x-1" : "text-gray-900"
                                  }`}>
                                  {pillar.title}
                                </h3>
                              </div>
                            </div>

                            {/* Collapsible Content */}
                            <div className={`grid transition-all duration-500 ease-in-out ${isExpanded ? "grid-rows-[1fr] opacity-100 mt-6" : "grid-rows-[0fr] opacity-0"
                              }`}>
                              <div className="overflow-hidden">
                                <p className="text-gray-600 text-sm leading-relaxed text-justify border-t border-black/5 pt-4">
                                  {pillar.description}
                                </p>
                              </div>
                            </div>
                          </button>
                        </div>
                      );
                    })}
                  </div>
                </ScrollReveal>
              </div>
            </section>
          </main>
        );
      })()}
      <Footer />
    </>
  );
}
