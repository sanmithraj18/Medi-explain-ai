import Link from 'next/link';
import {
  FileText, Shield, Brain, Clock, ChevronRight, Upload,
  CheckCircle, TrendingUp, Lock, Users, Star, ArrowRight,
  Activity, MessageSquare, Eye,
  AlertTriangle, Info
} from 'lucide-react';

// ─── Navbar ───────────────────────────────────────────────────────────────────
function Navbar() {
  return (
    <nav className="fixed top-0 inset-x-0 z-50 bg-white/95 backdrop-blur-sm border-b border-slate-100">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          <Link href="/" className="flex items-center gap-2.5">
            <div className="w-8 h-8 bg-gradient-to-br from-teal to-navy rounded-lg flex items-center justify-center">
              <Activity className="text-white" size={18} />
            </div>
            <span className="font-bold text-lg text-navy">MediExplain <span className="text-teal">AI</span></span>
          </Link>
          <div className="hidden md:flex items-center gap-8 text-sm font-medium text-blue-grey">
            <a href="#features" className="hover:text-navy transition-colors">Features</a>
            <a href="#how-it-works" className="hover:text-navy transition-colors">How It Works</a>
            <a href="#pricing" className="hover:text-navy transition-colors">Pricing</a>
            <a href="#faq" className="hover:text-navy transition-colors">FAQ</a>
          </div>
          <div className="flex items-center gap-3">
            <Link href="/login" className="text-sm font-medium text-navy hover:text-teal transition-colors px-3 py-2">
              Sign In
            </Link>
            <Link href="/register" className="btn-primary text-sm !py-2 !px-4">
              Get Started <ChevronRight size={16} />
            </Link>
          </div>
        </div>
      </div>
    </nav>
  );
}

// ─── Hero ──────────────────────────────────────────────────────────────────────
function HeroSection() {
  return (
    <section className="pt-32 pb-20 bg-gradient-to-br from-navy via-[#1e3a5f] to-[#0f3460] relative overflow-hidden">
      <div
        className="absolute inset-0 opacity-40"
        style={{
          backgroundImage: `url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%23ffffff' fill-opacity='0.03'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E")`,
        }}
      />
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 relative">
        <div className="max-w-3xl">
          <div className="inline-flex items-center gap-2 bg-teal/20 text-teal-light border border-teal/30 rounded-full px-4 py-1.5 text-sm font-medium mb-6">
            <Star size={14} />
            30-Day Free Trial · No Credit Card Required
          </div>
          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold text-white leading-tight mb-6">
            Understand Your<br />
            <span className="text-teal-light">Medical Reports.</span><br />
            Make Better-Informed<br />Conversations.
          </h1>
          <p className="text-lg text-slate-300 mb-10 max-w-xl leading-relaxed">
            Upload your laboratory report and receive easy-to-understand explanations,
            detailed parameter insights and questions to discuss with your doctor.
          </p>
          <div className="flex flex-col sm:flex-row gap-4">
            <Link href="/register" className="inline-flex items-center justify-center gap-2 bg-teal hover:bg-teal-dark text-white font-semibold px-8 py-3.5 rounded-xl transition-all duration-200 text-base shadow-lg shadow-teal/25">
              <Upload size={18} /> Explain My Report
            </Link>
            <Link href="/register" className="inline-flex items-center justify-center gap-2 bg-white/10 hover:bg-white/20 text-white font-semibold px-8 py-3.5 rounded-xl transition-all duration-200 text-base border border-white/20">
              Get Started Free <ArrowRight size={18} />
            </Link>
          </div>
          <p className="mt-6 text-sm text-slate-400 flex items-center gap-2">
            <CheckCircle size={14} className="text-teal-light" />
            Free for 30 days · Then ₹200/month · Cancel anytime
          </p>
        </div>
      </div>
      {/* Stats bar */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 mt-16 relative">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            { label: 'Report Types Supported', value: '7+' },
            { label: 'Parameters Explained', value: '50+' },
            { label: 'Trial Period', value: '30 Days' },
            { label: 'Monthly Price', value: '₹200' },
          ].map((stat) => (
            <div key={stat.label} className="bg-white/10 backdrop-blur-sm rounded-xl p-4 text-center border border-white/10">
              <p className="text-2xl font-bold text-white">{stat.value}</p>
              <p className="text-sm text-slate-300 mt-1">{stat.label}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

// ─── Features ─────────────────────────────────────────────────────────────────
const features = [
  {
    icon: FileText,
    title: 'Multi-Format Upload',
    desc: 'Upload PDF reports or image files (JPG, PNG). Camera scanning supported for physical documents.',
    color: 'text-teal',
  },
  {
    icon: Eye,
    title: 'Smart OCR Extraction',
    desc: 'Our pipeline extracts test names, values, units and reference ranges from both digital and scanned reports.',
    color: 'text-blue-500',
  },
  {
    icon: Brain,
    title: 'AI-Powered Explanations',
    desc: 'Get plain-language explanations of each parameter — what it measures and what your result means.',
    color: 'text-purple-500',
  },
  {
    icon: TrendingUp,
    title: 'Parameter Analysis',
    desc: 'Visual indicators show which parameters are within or outside the laboratory reference range.',
    color: 'text-teal',
  },
  {
    icon: MessageSquare,
    title: 'Doctor Discussion Guide',
    desc: "Auto-generated questions tailored to your specific results to help you have a more productive medical consultation.",
    color: 'text-orange-500',
  },
  {
    icon: Clock,
    title: 'Report History',
    desc: 'Securely store and access all your previous reports. Track how parameters change over time.',
    color: 'text-green-500',
  },
];

function FeaturesSection() {
  return (
    <section id="features" className="py-20 bg-white">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center mb-14">
          <h2 className="section-heading">Everything You Need to Understand Your Health</h2>
          <p className="section-subheading mx-auto">
            MediExplain AI transforms complex medical jargon into clear, actionable information.
          </p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {features.map((f) => (
            <div key={f.title} className="card-base hover:shadow-card-hover transition-shadow duration-200">
              <div className="w-11 h-11 rounded-xl bg-slate-50 flex items-center justify-center mb-4">
                <f.icon className={`w-5 h-5 ${f.color}`} />
              </div>
              <h3 className="font-semibold text-navy mb-2">{f.title}</h3>
              <p className="text-sm text-blue-grey leading-relaxed">{f.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

// ─── How It Works ─────────────────────────────────────────────────────────────
function HowItWorksSection() {
  const steps = [
    {
      step: '01',
      title: 'Upload Your Report',
      desc: 'Drag and drop a PDF or image, or use your camera to scan a physical report. Supported: CBC, Lipid Profile, Thyroid, Glucose, LFT, KFT, Vitamins and more.',
    },
    {
      step: '02',
      title: 'AI Analyses Your Results',
      desc: 'Our system extracts your test parameters, then uses AI to generate plain-language explanations with your actual values and reference ranges.',
    },
    {
      step: '03',
      title: 'Understand and Prepare',
      desc: "Review your overall summary, explore each parameter and get a personalised list of questions to bring to your next doctor's appointment.",
    },
  ];
  return (
    <section id="how-it-works" className="py-20 bg-surface">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center mb-14">
          <h2 className="section-heading">Simple. Secure. Helpful.</h2>
          <p className="section-subheading mx-auto">Three steps to understanding your medical report.</p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8 relative">
          <div className="hidden md:block absolute top-8 left-[calc(33%+2rem)] right-[calc(33%+2rem)] h-0.5 bg-gradient-to-r from-teal to-teal-light" />
          {steps.map((s) => (
            <div key={s.step} className="text-center relative">
              <div className="w-16 h-16 bg-gradient-to-br from-teal to-navy rounded-2xl flex items-center justify-center mx-auto mb-5 shadow-lg shadow-teal/20">
                <span className="text-white font-bold text-lg">{s.step}</span>
              </div>
              <h3 className="text-xl font-semibold text-navy mb-3">{s.title}</h3>
              <p className="text-blue-grey leading-relaxed text-sm">{s.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

// ─── Sample Report ────────────────────────────────────────────────────────────
function SampleReportSection() {
  const sampleParams = [
    {
      name: 'Haemoglobin',
      value: '11.2',
      unit: 'g/dL',
      range: '13.0 – 17.0',
      flag: 'L',
      explanation: "Haemoglobin carries oxygen in red blood cells. This result is below the laboratory's reference range for adult males. There are many possible reasons for this — your doctor is best placed to assess the significance in your context.",
    },
    {
      name: 'White Blood Cell Count',
      value: '8,200',
      unit: '/µL',
      range: '4,000 – 11,000',
      flag: 'N',
      explanation: 'White blood cells are part of the immune system. This result is within the laboratory reference range.',
    },
    {
      name: 'Fasting Glucose',
      value: '102',
      unit: 'mg/dL',
      range: '70 – 100',
      flag: 'H',
      explanation: "Blood glucose was measured after fasting. This result is slightly above the laboratory's reference range. A single elevated result does not diagnose diabetes — your doctor will consider this alongside other information.",
    },
  ];
  return (
    <section className="py-20 bg-white">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center mb-10">
          <div className="inline-flex items-center gap-2 bg-amber-50 text-amber-700 border border-amber-200 rounded-full px-4 py-1.5 text-sm font-medium mb-4">
            <Info size={14} />
            Sample Report — All Values Are Fictional
          </div>
          <h2 className="section-heading">See What MediExplain AI Explains</h2>
          <p className="section-subheading mx-auto">
            This is a demonstration using entirely fictional data. Real explanations are generated from your actual uploaded report.
          </p>
        </div>
        <div className="max-w-3xl mx-auto space-y-4">
          {sampleParams.map((p) => (
            <div key={p.name} className="card-base">
              <div className="flex items-start justify-between gap-4 mb-3">
                <div>
                  <h4 className="font-semibold text-navy">{p.name}</h4>
                  <div className="flex items-center gap-3 mt-1">
                    <span className="text-2xl font-bold text-navy">{p.value}</span>
                    <span className="text-sm text-blue-grey">{p.unit}</span>
                    <span className="text-xs text-slate-400">Ref: {p.range}</span>
                  </div>
                </div>
                <span className={`px-3 py-1 rounded-full text-xs font-semibold shrink-0 ${
                  p.flag === 'H' ? 'bg-red-100 text-red-700' :
                  p.flag === 'L' ? 'bg-blue-100 text-blue-700' :
                  'bg-green-100 text-green-700'
                }`}>
                  {p.flag === 'H' ? 'Above Range' : p.flag === 'L' ? 'Below Range' : 'Within Range'}
                </span>
              </div>
              <p className="text-sm text-blue-grey leading-relaxed border-t border-slate-100 pt-3">
                {p.explanation}
              </p>
            </div>
          ))}
          <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 flex gap-3">
            <AlertTriangle className="text-amber-600 shrink-0 mt-0.5" size={16} />
            <p className="text-sm text-amber-800">
              <strong>Medical Disclaimer:</strong> MediExplain AI explains laboratory results for informational purposes only. It does not diagnose conditions, prescribe medication or replace professional medical advice. Always consult your doctor about your results.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}

// ─── Privacy & Security ───────────────────────────────────────────────────────
function SecuritySection() {
  const points = [
    { icon: Lock, title: 'Private Storage', desc: "Your reports are stored in encrypted private storage. No public links. Only you can access your files." },
    { icon: Shield, title: 'Row-Level Security', desc: "Database-level access controls ensure one user can never access another user's reports." },
    { icon: CheckCircle, title: 'Secure Authentication', desc: 'Industry-standard authentication with email verification and optional Google Sign-In.' },
    { icon: Users, title: 'Your Data, Your Control', desc: 'Delete your reports and account at any time. Data retention policies are clearly disclosed.' },
  ];
  return (
    <section className="py-20 bg-navy">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center mb-14">
          <h2 className="text-3xl font-bold text-white mb-3">Your Medical Data is Private</h2>
          <p className="text-slate-300 text-lg max-w-2xl mx-auto">
            Medical information is among the most sensitive personal data. We take security seriously at every layer.
          </p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {points.map((p) => (
            <div key={p.title} className="bg-white/5 border border-white/10 rounded-xl p-6">
              <p.icon className="text-teal-light w-8 h-8 mb-4" />
              <h3 className="font-semibold text-white mb-2">{p.title}</h3>
              <p className="text-sm text-slate-400 leading-relaxed">{p.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

// ─── Pricing ──────────────────────────────────────────────────────────────────
function PricingSection() {
  return (
    <section id="pricing" className="py-20 bg-surface">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center mb-14">
          <h2 className="section-heading">Simple, Transparent Pricing</h2>
          <p className="section-subheading mx-auto">One plan. All features included. No hidden charges.</p>
        </div>
        <div className="max-w-md mx-auto">
          <div className="bg-white rounded-2xl shadow-card border-2 border-teal p-8 relative">
            <div className="absolute -top-3.5 left-1/2 -translate-x-1/2 bg-teal text-white text-sm font-semibold px-5 py-1 rounded-full whitespace-nowrap">
              Most Popular
            </div>
            <h3 className="text-xl font-bold text-navy mb-1">MediExplain AI Premium</h3>
            <div className="flex items-end gap-2 my-4">
              <span className="text-5xl font-bold text-navy">₹200</span>
              <span className="text-blue-grey mb-2">/month</span>
            </div>
            <p className="text-sm text-teal font-medium mb-6">30-day free trial · No payment required to start</p>
            <ul className="space-y-3 mb-8">
              {[
                'Unlimited report uploads',
                'PDF, JPG and PNG support',
                'Camera scanning',
                'AI-powered explanations',
                'Doctor discussion questions',
                'Full report history',
                'Parameter trend tracking',
                'Secure private storage',
              ].map((f) => (
                <li key={f} className="flex items-center gap-2.5 text-sm text-navy">
                  <CheckCircle className="text-teal shrink-0" size={16} />
                  {f}
                </li>
              ))}
            </ul>
            <Link href="/register" className="w-full btn-primary justify-center text-base !py-3">
              Start Free Trial <ArrowRight size={18} />
            </Link>
            <p className="text-xs text-slate-400 text-center mt-4">
              After the 30-day trial, ₹200/month is billed automatically.<br />
              You will be clearly shown the first debit date before authorizing payment.<br />
              Cancel anytime before your trial ends — no charge.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}

// ─── FAQ ──────────────────────────────────────────────────────────────────────
const faqs = [
  {
    q: 'What types of reports does MediExplain AI support?',
    a: 'Currently supported: Complete Blood Count (CBC), Lipid Profile, Thyroid Profile (TSH, T3, T4), Blood Glucose (fasting and HbA1c), Liver Function Test (LFT), Kidney Function Test (KFT) and common Vitamin panels. We aim to expand this list based on user feedback.',
  },
  {
    q: 'Can MediExplain AI diagnose my condition?',
    a: 'No. MediExplain AI does not diagnose medical conditions, prescribe medication or replace professional medical advice. It helps you understand what your test results mean and prepares you to have a more informed conversation with your doctor.',
  },
  {
    q: 'How is my medical data protected?',
    a: 'Your reports are stored in private, encrypted storage. Database-level row security ensures only you can access your data. Files are never publicly accessible. You can delete your reports and account at any time.',
  },
  {
    q: 'How does the 30-day free trial work?',
    a: 'When you register, your 30-day free trial begins automatically. You have full access to all features with no payment required during this period. If you choose to subscribe, you will be asked to authorize a recurring ₹200/month payment. Your first charge happens after the trial ends.',
  },
  {
    q: 'Can I cancel my subscription?',
    a: 'Yes. You can cancel at any time from your billing dashboard. If you cancel during the free trial, no charge will be made. If you cancel after a payment, you retain access until the end of the paid period.',
  },
  {
    q: 'What happens to my reports if I cancel?',
    a: 'Your uploaded reports are not deleted when you cancel. You retain access to view your report history. Premium analysis features will be unavailable until you resubscribe.',
  },
  {
    q: 'Is the AI explanation always accurate?',
    a: 'AI explanations are based on the values extracted from your report and general medical knowledge. They are for informational purposes and may not account for your complete medical history or clinical context. Always verify important medical information with your healthcare provider.',
  },
];

function FAQSection() {
  return (
    <section id="faq" className="py-20 bg-white">
      <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center mb-14">
          <h2 className="section-heading">Frequently Asked Questions</h2>
        </div>
        <div className="space-y-4">
          {faqs.map((faq, i) => (
            <details key={i} className="card-base cursor-pointer group">
              <summary className="font-semibold text-navy list-none flex items-center justify-between gap-4">
                {faq.q}
                <ChevronRight className="shrink-0 text-teal transition-transform group-open:rotate-90" size={18} />
              </summary>
              <p className="mt-3 text-sm text-blue-grey leading-relaxed border-t border-slate-100 pt-3">
                {faq.a}
              </p>
            </details>
          ))}
        </div>
      </div>
    </section>
  );
}

// ─── Disclaimer ───────────────────────────────────────────────────────────────
function DisclaimerSection() {
  return (
    <section className="py-12 bg-slate-50 border-y border-slate-200">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex gap-4">
          <AlertTriangle className="text-amber-500 shrink-0 mt-0.5" size={20} />
          <div>
            <h3 className="font-semibold text-navy mb-2">Medical Disclaimer</h3>
            <p className="text-sm text-blue-grey leading-relaxed">
              MediExplain AI is an informational tool designed to help users understand laboratory test results in plain language.
              It is not a medical device, does not provide medical diagnoses, and does not replace professional healthcare advice,
              diagnosis or treatment. Always seek the advice of your physician or other qualified health provider with any
              questions you may have regarding a medical condition. Never disregard professional medical advice or delay
              seeking it because of information provided by this service. If you believe you have a medical emergency,
              contact emergency services immediately.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}

// ─── Footer ───────────────────────────────────────────────────────────────────
function Footer() {
  return (
    <footer className="bg-navy py-12">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-8 mb-8">
          <div className="md:col-span-2">
            <div className="flex items-center gap-2.5 mb-3">
              <div className="w-7 h-7 bg-teal rounded-lg flex items-center justify-center">
                <Activity className="w-4 h-4 text-white" />
              </div>
              <span className="font-bold text-white">MediExplain AI</span>
            </div>
            <p className="text-sm text-slate-400 max-w-xs leading-relaxed">
              Your Reports. Simplified. Your Health Conversations. Empowered.
            </p>
          </div>
          <div>
            <h4 className="font-semibold text-white text-sm mb-3">Product</h4>
            <ul className="space-y-2 text-sm text-slate-400">
              <li><a href="#features" className="hover:text-white transition-colors">Features</a></li>
              <li><a href="#pricing" className="hover:text-white transition-colors">Pricing</a></li>
              <li><a href="#how-it-works" className="hover:text-white transition-colors">How It Works</a></li>
            </ul>
          </div>
          <div>
            <h4 className="font-semibold text-white text-sm mb-3">Legal</h4>
            <ul className="space-y-2 text-sm text-slate-400">
              <li><Link href="/privacy" className="hover:text-white transition-colors">Privacy Policy</Link></li>
              <li><Link href="/terms" className="hover:text-white transition-colors">Terms of Service</Link></li>
              <li><Link href="/refund" className="hover:text-white transition-colors">Refund Policy</Link></li>
            </ul>
          </div>
        </div>
        <div className="border-t border-white/10 pt-6 flex flex-col sm:flex-row justify-between items-center gap-3">
          <p className="text-sm text-slate-500">© 2026 MediExplain AI. All rights reserved.</p>
          <p className="text-xs text-slate-600">For informational purposes only. Not a substitute for professional medical advice.</p>
        </div>
      </div>
    </footer>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────
export default function LandingPage() {
  return (
    <div className="min-h-screen">
      <Navbar />
      <HeroSection />
      <FeaturesSection />
      <HowItWorksSection />
      <SampleReportSection />
      <SecuritySection />
      <PricingSection />
      <FAQSection />
      <DisclaimerSection />
      <Footer />
    </div>
  );
}
