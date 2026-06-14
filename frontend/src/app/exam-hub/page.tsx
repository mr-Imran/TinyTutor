"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  BookOpen,
  Calculator,
  FileQuestion,
  GraduationCap,
  Layers,
  Mic,
  Presentation,
  Sparkles,
  Target,
  TrendingUp,
} from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { HumanText } from "@/components/HumanText";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { api, CgpaCourse, SemesterDashboard } from "@/lib/api";

const PdfReader = dynamic(() => import("@/components/PdfReader").then((m) => m.PdfReader), {
  ssr: false,
  loading: () => <Skeleton className="h-96" />,
});

function ToolRunner({
  title,
  onRun,
  needsTopic = true,
}: {
  title: string;
  onRun: (topic: string) => Promise<
    | string
    | Array<string | { title?: string; question?: string; question_type?: string; answers?: string[] }>
    | { pairs: { question: string; model_answer: string }[] }
  >;
  needsTopic?: boolean;
}) {
  const [topic, setTopic] = useState("");
  const [topics, setTopics] = useState<string[]>([]);
  const [result, setResult] = useState("");
  const [list, setList] = useState<Array<string | { title?: string; question?: string; question_type?: string; answers?: string[] }>>([]);
  const [viva, setViva] = useState<{ question: string; model_answer: string }[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.topics().then((r) => {
      setTopics(r.topics);
      if (r.topics[0]) setTopic(r.topics[0]);
    });
  }, []);

  const run = async () => {
    setLoading(true);
    setResult("");
    setList([]);
    setViva([]);
    try {
      const out = await onRun(topic);
      if (typeof out === "string") setResult(out);
      else if (Array.isArray(out)) setList(out);
      else if (out && "pairs" in out) setViva(out.pairs);
    } catch (e) {
      setResult(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {needsTopic && (
          <select
            className="w-full rounded-lg border border-white/15 bg-white/5 px-3 py-2 text-sm"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
          >
            {topics.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        )}
        <Button onClick={run} disabled={loading || (needsTopic && !topic)}>
          {loading ? "Working…" : "Run"}
        </Button>
        {result && <HumanText text={result} className="text-muted-foreground" />}
        {list.length > 0 && (
          <ol className="list-decimal space-y-2 pl-5 text-sm text-muted-foreground">
            {list.map((q, i) => {
              if (typeof q === "string") {
                return <li key={i}>{q}</li>;
              }

              if (q && typeof q === "object") {
                const title = q.title || q.question || "Question";
                const details = q.answers ? ` Answers: ${q.answers.join(", ")}` : q.question_type ? ` (${q.question_type})` : "";
                return <li key={i}>{title + details}</li>;
              }

              return <li key={i}>{String(q)}</li>;
            })}
          </ol>
        )}
        {viva.length > 0 && (
          <div className="space-y-4">
            {viva.map((p, i) => (
              <div key={i} className="rounded-lg bg-white/5 p-3">
                <p className="text-sm font-medium text-violet-300">Q: {p.question}</p>
                <HumanText text={p.model_answer} className="mt-2 text-muted-foreground" />
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default function ExamHubPage() {
  const [semester, setSemester] = useState<SemesterDashboard | null>(null);
  const [courses, setCourses] = useState<CgpaCourse[]>([
    { name: "Course 1", credit: 3, grade_point: 3.5 },
  ]);
  const [cgpa, setCgpa] = useState<number | null>(null);

  useEffect(() => {
    api.semesterDashboard().then(setSemester).catch(console.error);
  }, []);

  const addCourse = () => setCourses([...courses, { name: `Course ${courses.length + 1}`, credit: 3, grade_point: 3.0 }]);

  const calcCgpa = async () => {
    const res = await api.calculateCgpa(courses);
    setCgpa(res.cgpa);
  };

  return (
    <div>
      <PageHeader
        title="Exam Hub"
        description="Previous papers, PPT analysis, CQ generator, predictors, viva practice, CGPA, PDF reader, and semester overview."
      />

      <Tabs defaultValue="semester" className="w-full">
        <TabsList className="mb-2 h-auto flex-wrap">
          <TabsTrigger value="semester">Semester</TabsTrigger>
          <TabsTrigger value="pdf">PDF Reader</TabsTrigger>
          <TabsTrigger value="prev">Past Papers</TabsTrigger>
          <TabsTrigger value="ppt">PPT</TabsTrigger>
          <TabsTrigger value="cq">CQ</TabsTrigger>
          <TabsTrigger value="mid">Midterm</TabsTrigger>
          <TabsTrigger value="final">Final</TabsTrigger>
          <TabsTrigger value="viva">Viva</TabsTrigger>
          <TabsTrigger value="cgpa">CGPA</TabsTrigger>
        </TabsList>

        <TabsContent value="semester">
          {!semester ? (
            <Skeleton className="h-64" />
          ) : (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="grid gap-4 md:grid-cols-2">
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <Target className="h-4 w-4 text-violet-400" />
                    Readiness score
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-4xl font-bold">{semester.readiness_score}%</p>
                  <Progress value={semester.readiness_score} className="mt-3" />
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <BookOpen className="h-4 w-4" />
                    Materials
                  </CardTitle>
                </CardHeader>
                <CardContent className="text-sm text-muted-foreground">
                  <p>{semester.pdf_count} PDFs · {semester.ppt_count} PPTX · {semester.documents.length} total</p>
                  {semester.study_targets.has_plan && (
                    <p className="mt-2">
                      Study goal: {semester.study_targets.hours_per_day}h/day · CGPA target{" "}
                      {semester.study_targets.expected_cgpa}
                    </p>
                  )}
                </CardContent>
              </Card>
              <Card className="md:col-span-2">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base text-amber-400">
                    <TrendingUp className="h-4 w-4" />
                    Weak topic tracking
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  {semester.weak_topics.length === 0 ? (
                    <p className="text-sm text-muted-foreground">Take quizzes to track weak areas.</p>
                  ) : (
                    semester.weak_topics.map((t) => (
                      <div key={t.topic}>
                        <div className="mb-1 flex justify-between text-sm">
                          <span>{t.topic}</span>
                          <span>{t.mastery_percentage}%</span>
                        </div>
                        <Progress value={t.mastery_percentage} />
                      </div>
                    ))
                  )}
                </CardContent>
              </Card>
            </motion.div>
          )}
        </TabsContent>

        <TabsContent value="pdf">
          <PdfReader />
        </TabsContent>

        <TabsContent value="prev">
          <ToolRunner
            title="Previous question analysis"
            needsTopic={false}
            onRun={async (topic) => (await api.analyzePreviousQuestions(topic || undefined)).analysis}
          />
        </TabsContent>

        <TabsContent value="ppt">
          <ToolRunner
            title="Teacher PPT analysis"
            needsTopic={false}
            onRun={async (topic) => (await api.analyzePpt(topic || undefined)).analysis}
          />
        </TabsContent>

        <TabsContent value="cq">
          <ToolRunner
            title="CQ question generator"
            onRun={async (topic) => (await api.generateCq(topic, 5)).questions}
          />
        </TabsContent>

        <TabsContent value="mid">
          <ToolRunner
            title="Midterm predictor"
            needsTopic={false}
            onRun={async (topic) => (await api.predictMidterm(topic || undefined)).prediction}
          />
        </TabsContent>

        <TabsContent value="final">
          <ToolRunner
            title="Final predictor"
            needsTopic={false}
            onRun={async (topic) => (await api.predictFinal(topic || undefined)).prediction}
          />
        </TabsContent>

        <TabsContent value="viva">
          <ToolRunner
            title="Viva simulator"
            onRun={async (topic) => (await api.vivaSimulator(topic, 5)) as { pairs: { question: string; model_answer: string }[] }}
          />
        </TabsContent>

        <TabsContent value="cgpa">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Calculator className="h-5 w-5 text-cyan-400" />
                CGPA calculator
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {courses.map((c, i) => (
                <div key={i} className="grid gap-2 sm:grid-cols-4">
                  <Input
                    placeholder="Course name"
                    value={c.name}
                    onChange={(e) => {
                      const copy = [...courses];
                      copy[i].name = e.target.value;
                      setCourses(copy);
                    }}
                  />
                  <Input
                    type="number"
                    placeholder="Credits"
                    value={c.credit}
                    onChange={(e) => {
                      const copy = [...courses];
                      copy[i].credit = parseFloat(e.target.value) || 0;
                      setCourses(copy);
                    }}
                  />
                  <Input
                    type="number"
                    step="0.01"
                    placeholder="Grade point"
                    value={c.grade_point}
                    onChange={(e) => {
                      const copy = [...courses];
                      copy[i].grade_point = parseFloat(e.target.value) || 0;
                      setCourses(copy);
                    }}
                  />
                </div>
              ))}
              <div className="flex gap-2">
                <Button variant="outline" onClick={addCourse}>
                  Add course
                </Button>
                <Button onClick={calcCgpa}>Calculate CGPA</Button>
              </div>
              {cgpa !== null && (
                <p className="text-2xl font-bold">
                  Your CGPA: <span className="text-cyan-400">{cgpa}</span>
                </p>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <div className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {[
          { icon: FileQuestion, label: "Past papers", tab: "prev" },
          { icon: Presentation, label: "PPT analysis", tab: "ppt" },
          { icon: Layers, label: "CQ generator", tab: "cq" },
          { icon: GraduationCap, label: "Midterm", tab: "mid" },
          { icon: Sparkles, label: "Final", tab: "final" },
          { icon: Mic, label: "Viva", tab: "viva" },
        ].map(({ icon: Icon, label }) => (
          <div key={label} className="flex items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs text-muted-foreground">
            <Icon className="h-3.5 w-3.5 text-violet-400" />
            {label} — ready
          </div>
        ))}
      </div>
    </div>
  );
}
