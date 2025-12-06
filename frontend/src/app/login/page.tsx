"use client";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { supabase } from "@/lib/supabase";

export default function Login() {
  const handleGoogleSignIn = async () => {
    supabase.auth.signInWithOAuth({
      provider: "google",
      options: {
        redirectTo: `${window.location.origin}/dashboard`,
      },
    });
  };

  return (
    <div className="flex justify-center items-center min-h-screen">
      <Card className="w-full max-w-sm items-center">
        <CardHeader className="items-center gap-4">
          <CardTitle className="text-2xl">Sign in to Bro</CardTitle>
          <Button
            variant="outline"
            className="w-full"
            onClick={handleGoogleSignIn}>Sign in with Google
          </Button>
        </CardHeader>
        <CardContent>
          <div className="flex items-center text-sm">
            <Separator className="flex-1" />
            Or sign in with email
            <Separator className="flex-1" />

          </div>
          {/* TODO */}
          <form>
            <div className="flex flex-col gap-4">
              <div className="grid gap-2">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  placeholder="joe@gmail.com"
                  required
                />
              </div>
              <div className="grid gap-2">
                <div className="flex items-center">
                  <Label htmlFor="password">Password</Label>
                  <a
                    href="#"
                    className="ml-auto inline-block text-sm underline-offset-4 hover:underline"
                  >
                    Forgot your password?
                  </a>
                </div>
                <Input id="password" type="password" required />
              </div>
            </div>
          </form>
        </CardContent>
        <CardFooter className="flex-col gap-2">
          <Button variant="outline" className="w-full">Sign in</Button>
        </CardFooter>
      </Card>
    </div>

  );
}
