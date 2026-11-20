package com.realitycontrol.vpn;

import android.animation.ValueAnimator;
import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.view.View;
import android.view.animation.LinearInterpolator;

final class PowerHaloView extends View {
    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private ValueAnimator animator;
    private String phase = "disconnected";
    private float progress;
    private boolean motionAllowed = true;
    PowerHaloView(Context c) { super(c); setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_NO); }
    void setPhase(String value) { if (!phase.equals(value)) { phase = value; stop(); refreshMotion(); invalidate(); } }
    void setMotionAllowed(boolean value) { motionAllowed = value; if (value) refreshMotion(); else stop(); }
    private void refreshMotion() {
        if (animator != null || !motionAllowed || phase.equals("disconnected") || !isAttachedToWindow() || getWindowVisibility() != VISIBLE || !ValueAnimator.areAnimatorsEnabled()) return;
        animator = ValueAnimator.ofFloat(0, 1); animator.setDuration(phase.equals("connected") ? 2400 : 1200); animator.setRepeatCount(ValueAnimator.INFINITE); animator.setInterpolator(new LinearInterpolator());
        animator.addUpdateListener(a -> { progress = (float) a.getAnimatedValue(); invalidate(); }); animator.start();
    }
    private void stop() { if (animator != null) { animator.cancel(); animator = null; } progress = 0; }
    @Override protected void onAttachedToWindow() { super.onAttachedToWindow(); refreshMotion(); }
    @Override protected void onDetachedFromWindow() { stop(); super.onDetachedFromWindow(); }
    @Override protected void onWindowVisibilityChanged(int visibility) { super.onWindowVisibilityChanged(visibility); if (visibility == VISIBLE) refreshMotion(); else stop(); }
    @Override protected void onDraw(Canvas canvas) {
        super.onDraw(canvas); float cx = getWidth() / 2f, cy = getHeight() / 2f, radius = Math.min(cx, cy) - 4 * getResources().getDisplayMetrics().density;
        paint.setStyle(Paint.Style.STROKE); paint.setStrokeWidth(2 * getResources().getDisplayMetrics().density);
        paint.setColor(phase.equals("connected") ? 0xff85d9b7 : 0xffad9af1); paint.setAlpha(45); canvas.drawCircle(cx, cy, radius, paint);
        if (phase.equals("connecting") || phase.equals("disconnecting")) { paint.setAlpha(190); canvas.drawArc(cx - radius, cy - radius, cx + radius, cy + radius, progress * 360 - 90, 100, false, paint); }
        else if (phase.equals("connected")) { paint.setAlpha((int) (100 * (1 - progress))); canvas.drawCircle(cx, cy, radius - 5 + progress * 5, paint); }
    }
}
