"use client";
import { useState, useEffect } from "react";


import Image from "next/image";
import ScrollReveal from "../components/ScrollReveal";
import ResourcesSkeleton from "../components/ResourcesSkeleton";
import { useLanguage } from "../lib/i18n/LanguageContext";
import {
    Zap,
    Activity,
    Cpu,
    Table,
    Flame,
    Hash,
    HardDrive,
    ExternalLink,
    Bot,
    FastForward,
    Sparkles,
    Brain,
    Database,
    Server,
    FileCode,
    FileText,
    Globe,
    Triangle,
    Github,
    GitBranch,
    Cloud,
    Terminal,
    Landmark,
    Building2,
    Newspaper,
    Search,
    Code,
    Palette,
    LineChart,
    MapPin,
    Map,
    RefreshCw,
    Feather,
    ShieldCheck,
    ArrowRight
} from "lucide-react";

interface ResourceItem {
    name: string;
    description: string;
    icon: React.ComponentType<{ className?: string }>;
    logo?: string;
    link: string;
}

interface ResourceGroup {
    title: string;
    resources: ResourceItem[];
}

const resourceGroups: ResourceGroup[] = [
    {
        title: "Machine Learning & Time-Series Modeling",
        resources: [
            {
                name: "LightGBM",
                description: "High-performance gradient boosting framework using tree-based learning algorithms for fast, accurate tabular agri-fishery price predictions.",
                icon: Zap,
                logo: "https://raw.githubusercontent.com/microsoft/LightGBM/master/docs/logo/LightGBM_logo_black_text.svg",
                link: "https://lightgbm.readthedocs.io/"
            },
            {
                name: "PyTorch",
                description: "Open-source deep learning framework providing tensor computation and deep neural network acceleration for predictive research.",
                icon: Flame,
                logo: "https://cdn.simpleicons.org/pytorch/EE4C2C",
                link: "https://pytorch.org/"
            },
            {
                name: "LSTM",
                description: "Long Short-Term Memory recurrent neural network architecture optimized for capturing sequential dependencies and temporal price trends.",
                icon: Activity,
                logo: "https://cdn.simpleicons.org/pytorch/EE4C2C",
                link: "https://pytorch.org/docs/stable/generated/torch.nn.LSTM.html"
            },
            {
                name: "Scikit-learn",
                description: "Comprehensive machine learning toolkit for feature preprocessing, standard scaling, and multi-horizon validation metrics.",
                icon: Cpu,
                logo: "https://cdn.simpleicons.org/scikitlearn",
                link: "https://scikit-learn.org/"
            },
            {
                name: "Pandas",
                description: "Fast, powerful data manipulation tool used to build multi-variate time-series matrices and clean historical price observations.",
                icon: Table,
                logo: "https://cdn.simpleicons.org/pandas/150458",
                link: "https://pandas.pydata.org/"
            },
            {
                name: "NumPy",
                description: "Fundamental scientific computing package powering multi-dimensional arrays, mathematical vectorization, and loss calculations.",
                icon: Hash,
                logo: "https://cdn.simpleicons.org/numpy/013243",
                link: "https://numpy.org/"
            },
            {
                name: "Joblib",
                description: "Pipelining, disk-caching, and parallel execution toolkit for persisting and loading trained model checkpoints and scalers.",
                icon: HardDrive,
                logo: "https://cdn.simpleicons.org/python/3776AB",
                link: "https://joblib.readthedocs.io/"
            },
            {
                name: "HTTPX",
                description: "Fully featured async HTTP client for Python, handling fast asynchronous data transport and pipeline orchestration.",
                icon: ExternalLink,
                logo: "https://cdn.simpleicons.org/python/3776AB",
                link: "https://www.python-httpx.org/"
            }
        ]
    },
    {
        title: "AI Models & Intelligent Analysis",
        resources: [
            {
                name: "Google Gemini",
                description: "Advanced multimodal reasoning model providing context-aware supply insights, agricultural summaries, and market reasoning.",
                icon: Bot,
                logo: "https://cdn.simpleicons.org/googlegemini/8E75B2",
                link: "https://deepmind.google/technologies/gemini/"
            },
            {
                name: "Groq AI",
                description: "Ultra-low latency LPU inference platform powering lightning-fast LLM generation and live price anomaly analysis.",
                icon: FastForward,
                logo: "https://cdn.simpleicons.org/fastapi/009688",
                link: "https://groq.com/"
            },
            {
                name: "Hermes Agent",
                description: "Autonomous AI research and implementation agent driving systematic model audits, performance optimization, and pipeline validation.",
                icon: Brain,
                logo: "https://cdn.simpleicons.org/robotframework",
                link: "https://nousresearch.com/"
            },
            {
                name: "Anthropic Claude",
                description: "Advanced AI research assistant utilized for code synthesis, architectural refactoring, and statistical verification.",
                icon: Sparkles,
                logo: "https://cdn.simpleicons.org/anthropic",
                link: "https://www.anthropic.com/"
            }
        ]
    },
    {
        title: "Backend, Database & Cloud Infrastructure",
        resources: [
            {
                name: "Supabase",
                description: "Open-source backend platform providing managed PostgreSQL, Row-Level Security (RLS), edge APIs, and real-time database capabilities.",
                icon: Database,
                logo: "https://cdn.simpleicons.org/supabase",
                link: "https://supabase.com/"
            },
            {
                name: "PostgreSQL",
                description: "Enterprise-grade relational database management system storing historical market prices, calibrated prediction intervals, and audit trails.",
                icon: Database,
                logo: "https://cdn.simpleicons.org/postgresql",
                link: "https://www.postgresql.org/"
            },
            {
                name: "Supabase Edge Functions",
                description: "Globally distributed serverless functions running on Deno for sub-100ms API routing, live forecasting, and cache deduplication.",
                icon: Server,
                logo: "https://cdn.simpleicons.org/deno",
                link: "https://supabase.com/docs/guides/functions"
            },
            {
                name: "Deno",
                description: "Secure modern JavaScript and TypeScript runtime executing low-latency Edge compute logic with zero cold starts.",
                icon: Server,
                logo: "https://cdn.simpleicons.org/deno",
                link: "https://deno.com/"
            },
            {
                name: "Python",
                description: "Core backend language powering the entire machine learning pipeline, statistical validation suites, and data ingestion.",
                icon: FileCode,
                logo: "https://cdn.simpleicons.org/python",
                link: "https://www.python.org/"
            },
            {
                name: "Node.js",
                description: "Cross-platform JavaScript runtime executing frontend server components, API load tests, and build tooling.",
                icon: Terminal,
                logo: "https://cdn.simpleicons.org/nodedotjs",
                link: "https://nodejs.org/"
            },
            {
                name: "Vercel",
                description: "Frontend cloud platform providing automated deployments, global edge CDN distribution, and continuous performance monitoring.",
                icon: Triangle,
                logo: "https://cdn.simpleicons.org/vercel",
                link: "https://vercel.com/"
            },
            {
                name: "Cloudflare",
                description: "Global cloud network providing DNS routing, edge security, and distributed object storage for media assets.",
                icon: Cloud,
                logo: "https://cdn.simpleicons.org/cloudflare",
                link: "https://www.cloudflare.com/"
            }
        ]
    },
    {
        title: "Data Acquisition, Extraction & Monitoring",
        resources: [
            {
                name: "Dept. of Agriculture (DA)",
                description: "Principal government department responsible for Philippine agri-fishery governance and official retail price monitoring across Metro Manila.",
                icon: Landmark,
                logo: "https://www.da.gov.ph/wp-content/uploads/2021/04/DA-Logo-150x150.png",
                link: "https://www.da.gov.ph/"
            },
            {
                name: "DA AMAS",
                description: "Agribusiness and Marketing Assistance Service, the primary surveillance division monitoring retail wet market prices across NCR.",
                icon: Building2,
                logo: "https://www.da.gov.ph/wp-content/uploads/2021/04/DA-Logo-150x150.png",
                link: "https://agribusiness.da.gov.ph/"
            },
            {
                name: "pdfplumber",
                description: "Python library used for high-precision extraction of tabular commodity and price data from official daily PDF price bulletins.",
                icon: FileText,
                logo: "https://cdn.simpleicons.org/python/3776AB",
                link: "https://github.com/jsvine/pdfplumber"
            },
            {
                name: "BeautifulSoup",
                description: "Python web scraping package used for parsing HTML and extracting real-time agricultural headlines and news reports.",
                icon: FileCode,
                logo: "https://cdn.simpleicons.org/python/3776AB",
                link: "https://www.crummy.com/software/BeautifulSoup/"
            },
            {
                name: "Crawl4AI",
                description: "Open-source LLM-friendly web crawler automating reliable gathering of market news and commodity intelligence.",
                icon: Search,
                logo: "https://cdn.simpleicons.org/gnubash",
                link: "https://crawl4ai.com/"
            },
            {
                name: "ABS-CBN News",
                description: "National news organization monitored for supply chain disruptions, typhoons, inflation trends, and retail food price alerts.",
                icon: Newspaper,
                logo: "https://cdn.simpleicons.org/rss",
                link: "https://news.abs-cbn.com/"
            },
            {
                name: "Philippine News Agency",
                description: "Official news agency of the Philippine government, supplying verified agricultural policies, harvest forecasts, and trade reports.",
                icon: Newspaper,
                logo: "https://cdn.simpleicons.org/rss",
                link: "https://www.pna.gov.ph/"
            }
        ]
    },
    {
        title: "Frontend Development & User Experience",
        resources: [
            {
                name: "Next.js 16",
                description: "Cutting-edge React framework leveraging App Router, React Server Components, and Incremental Static Regeneration for blazing fast rendering.",
                icon: Globe,
                logo: "https://cdn.simpleicons.org/nextdotjs",
                link: "https://nextjs.org/"
            },
            {
                name: "React 19",
                description: "Industry-standard component library powering interactive client interfaces, concurrent rendering, and reactive state management.",
                icon: Code,
                logo: "https://cdn.simpleicons.org/react",
                link: "https://react.dev/"
            },
            {
                name: "TypeScript",
                description: "Strongly typed programming language ensuring end-to-end data integrity across database schemas, API routes, and UI components.",
                icon: FileCode,
                logo: "https://cdn.simpleicons.org/typescript",
                link: "https://www.typescriptlang.org/"
            },
            {
                name: "Tailwind CSS v4",
                description: "Utility-first modern CSS framework providing custom styling, responsive layouts, and cohesive brand design tokens.",
                icon: Palette,
                logo: "https://cdn.simpleicons.org/tailwindcss",
                link: "https://tailwindcss.com/"
            },
            {
                name: "Recharts",
                description: "Composable SVG charting library built on React components for displaying interactive historical prices and multi-horizon forecasts.",
                icon: LineChart,
                logo: "https://cdn.simpleicons.org/react/61DAFB",
                link: "https://recharts.org/"
            },
            {
                name: "Lightweight Charts",
                description: "High-performance HTML5 Canvas financial charting library delivering fluid price analysis graphs and crosshair tooltips.",
                icon: Activity,
                logo: "https://cdn.simpleicons.org/tradingview",
                link: "https://tradingview.github.io/lightweight-charts/"
            },
            {
                name: "Leaflet",
                description: "Mobile-friendly interactive mapping library powering the Metro Manila wet market geographical locator and price heatmaps.",
                icon: MapPin,
                logo: "https://cdn.simpleicons.org/leaflet",
                link: "https://leafletjs.com/"
            },
            {
                name: "OpenStreetMap",
                description: "Open spatial database providing free geographic cartography, street tiles, and coordinate metadata for NCR markets.",
                icon: Map,
                logo: "https://cdn.simpleicons.org/openstreetmap",
                link: "https://www.openstreetmap.org/"
            },
            {
                name: "SWR",
                description: "React Hooks for data fetching with stale-while-revalidate caching, request deduplication, and automated background refresh.",
                icon: RefreshCw,
                logo: "https://cdn.simpleicons.org/swr",
                link: "https://swr.vercel.app/"
            },
            {
                name: "Lucide Icons",
                description: "Crisp, consistent, and customizable SVG icon suite enhancing visual accessibility and clear navigational cues.",
                icon: Feather,
                logo: "https://cdn.simpleicons.org/lucide",
                link: "https://lucide.dev/"
            }
        ]
    },
    {
        title: "DevOps & Engineering Tools",
        resources: [
            {
                name: "GitHub",
                description: "Cloud platform for source code management, collaborative Git version control, issue tracking, and repository storage.",
                icon: Github,
                logo: "https://cdn.simpleicons.org/github",
                link: "https://github.com/"
            },
            {
                name: "GitHub Actions",
                description: "Automated CI/CD workflow platform executing test suites, model verification checks, and build validation on every commit.",
                icon: GitBranch,
                logo: "https://cdn.simpleicons.org/githubactions",
                link: "https://github.com/features/actions"
            },
            {
                name: "Git",
                description: "Distributed version control system managing experiment branches, model audits, commit history, and code merges.",
                icon: GitBranch,
                logo: "https://cdn.simpleicons.org/git",
                link: "https://git-scm.com/"
            },
            {
                name: "ESLint",
                description: "Static code analysis tool identifying code smells, anti-patterns, and enforcing consistent JavaScript and TypeScript standards.",
                icon: ShieldCheck,
                logo: "https://cdn.simpleicons.org/eslint",
                link: "https://eslint.org/"
            }
        ]
    }
];

function ResourceCard({ resource }: { resource: any }) {
    const Icon = resource.icon;
    const [imgError, setImgError] = useState(false);
    const { t } = useLanguage();

    return (
        <div className="bg-white rounded-[1.5rem] sm:rounded-[2rem] p-8 sm:p-10 shadow-[0_8px_30px_rgb(0,0,0,0.04)] border border-gray-50 flex flex-col h-full min-h-[300px] transition-all duration-300 hover:shadow-[0_20px_50px_rgba(0,0,0,0.08)]">
            <div className="flex items-center gap-5 mb-5">
                <div className="relative w-14 h-14 sm:w-16 sm:h-16 bg-gray-50 rounded-2xl flex items-center justify-center shrink-0 overflow-hidden p-3">
                    {resource.logo && !imgError ? (
                        <Image 
                            src={resource.logo} 
                            alt={resource.name} 
                            fill
                            unoptimized
                            className="object-contain p-3"
                            style={{ display: imgError ? 'none' : 'block' }}
                            onError={() => setImgError(true)}
                        />
                    ) : (
                        <div className="flex items-center justify-center w-full h-full animate-fade-in">
                            <Icon className="w-7 h-7 text-orange" />
                        </div>
                    )}
                </div>
                <h3 className="text-xl sm:text-2xl font-bold text-[#0B3D2E]" style={{ fontFamily: "var(--font-display)" }}>
                    {resource.name}
                </h3>
            </div>

            <p className="text-gray-500 text-sm sm:text-base leading-relaxed mb-8 flex-grow">
                {resource.description}
            </p>

            <a
                href={resource.link}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 text-[#0B3D2E] text-xs sm:text-sm font-bold uppercase tracking-wider hover:text-orange transition-colors group"
            >
                {t("learnMore")}
                <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />
            </a>
        </div>
    );
}

function SectionHeading({ title }: { title: string }) {
    return (
        <div className="flex items-center gap-4 mb-8 sm:mb-12">
            <div className="h-[2px] w-12 sm:w-16 bg-primary-800/20" />
            <h2 className="text-2xl sm:text-4xl font-bold text-[#0B3D2E]" style={{ fontFamily: "var(--font-display)" }}>
                {title}
            </h2>
        </div>
    );
}

export default function ResourcesPage() {
    const [isLoading, setIsLoading] = useState(true);
    const { t, isTransitioning } = useLanguage();

    useEffect(() => {
        const timer = setTimeout(() => setIsLoading(false), 200);
        return () => clearTimeout(timer);
    }, []);

    if (isLoading || isTransitioning) {
        return <ResourcesSkeleton />;
    }

    return (
        <div className="flex flex-col min-h-screen bg-surface">

            <main id="main-content" className="flex-grow">
                {/* Hero */}
                <section className="relative py-12 sm:py-20 pt-28 sm:pt-36 overflow-hidden bg-primary-900">
                    <div className="absolute inset-0">
                        <Image
                            src="/Bg-4.jpg"
                            alt="background"
                            fill
                            priority
                            className="object-cover blur-sm scale-105 opacity-60"
                        />
                        <div className="absolute inset-0 bg-primary-900/60" />
                    </div>
                    <div className="relative z-10 max-w-[90rem] mx-auto px-5 lg:px-10">
                        <ScrollReveal animation="fade-up">
                            <h1
                                className="text-3xl sm:text-4xl lg:text-6xl font-bold text-white mb-4"
                                style={{ fontFamily: "var(--font-display)" }}
                            >
                                {t("resources")} <span className="text-white/60">&</span> <br className="sm:hidden" />
                                <span className="text-transparent bg-clip-text bg-gradient-to-r from-accent-light to-accent">
                                    {t("references")}
                                </span>
                            </h1>
                            <p className="text-white/60 max-w-2xl text-sm sm:text-lg leading-relaxed">
                                {t("resourcesDesc")}
                            </p>
                        </ScrollReveal>
                    </div>
                </section>

                {/* Groups Content */}
                <section className="py-12 sm:py-20">
                    <div className="max-w-[90rem] mx-auto px-5 lg:px-10 space-y-16 sm:space-y-24">
                        {resourceGroups.map((group, groupIdx) => (
                            <div key={groupIdx}>
                                <ScrollReveal animation="fade-in" delay={100}>
                                    <SectionHeading title={group.title} />
                                </ScrollReveal>
                                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8 sm:gap-10">
                                    {group.resources.map((resource, idx) => (
                                        <ScrollReveal key={idx} animation="fade-up" delay={150 + (idx * 50)}>
                                            <ResourceCard resource={resource} />
                                        </ScrollReveal>
                                    ))}
                                </div>
                            </div>
                        ))}
                    </div>
                </section>
            </main>

        </div>
    )
}
