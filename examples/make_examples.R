# Sample plots for the FigAssemble tutorial: made-up data, saved the way an R notebook saves a
# figure (PDF, PNG at 600 dpi and SVG under one name), so FigAssemble finds all three copies.
#
#   Rscript examples/make_examples.R      (from the repository's top folder)
#
# Style as in Matthew's figures: theme_classic, Helvetica at base size 6, transparent
# backgrounds, margins cropped to the ink, 0.2 cm legend keys. Each panel has its own random
# seed, and the jitter a fixed one, so the three copies of a plot are identical and re-running
# the script makes the same plots.

library(data.table)
library(ggplot2)
library(magrittr)

# Setup ---------------------------------------------------------------------------------------

# Measuring text opens a graphics device; a null one keeps R from leaving an Rplots.pdf behind
pdf(NULL)

# Colour-blind-safe colours (Okabe-Ito)
okabe_ito <- c("#E69F00", "#56B4E9", "#009E73", "#0072B2", "#D55E00", "#CC79A7")
out_dir <- "examples"

# The house theme: base size 6 in Helvetica, nothing painted behind the plot
theme_figure <- function() {
  return(theme_classic(base_size = 6, base_family = "Helvetica") +
    theme(plot.background = element_rect(fill = NA, color = NA),
          panel.background = element_rect(fill = NA, color = NA),
          legend.background = element_blank(),
          legend.box.background = element_blank(),
          legend.key.size = unit(0.2, "cm"),
          legend.margin = margin(0, 0, 0, 0),
          legend.box.spacing = unit(2, "pt"),
          plot.margin = margin(0, 0, 0, 0)))
}

# Smallest margins that keep everything inside a figure of the given size (as in
# Matthew's analysis notebooks); returns the plot and its size
fit_margins <- function(plot, width = NULL, height = NULL, sides = c("t", "r", "b", "l"), pad_pt = 0.5, res = 300) {
  margins <- c(t = 0, r = 0, b = 0, l = 0)
  old_dev <- grDevices::dev.cur()
  set_margins <- function(m) {
    plot + ggplot2::theme(plot.margin = ggplot2::margin(m[["t"]], m[["r"]], m[["b"]], m[["l"]], unit = "in"))
  }
  added_up <- function(g) {
    c(w = sum(grid::convertWidth(g$widths, "in", valueOnly = TRUE)),
      h = sum(grid::convertHeight(g$heights, "in", valueOnly = TRUE)))
  }
  ink_edges <- function(g, w, h, room, dpi) {
    # Draw g at w x h in on a transparent canvas with `room` in around it; how far the ink reaches
    cap <- ragg::agg_capture(width = w + 2 * room, height = h + 2 * room, units = "in", res = dpi, background = "transparent")
    grid::pushViewport(grid::viewport(x = grid::unit(room, "in"), y = grid::unit(room, "in"),
                                      width = grid::unit(w, "in"), height = grid::unit(h, "in"), just = c("left", "bottom")))
    grid::grid.draw(g)
    px <- cap(native = TRUE)
    grDevices::dev.off()
    if (old_dev > 1) grDevices::dev.set(old_dev)
    px_dim <- dim(px)
    px <- as.vector(unclass(px))
    ink <- matrix(is.na(px) | px != 0L, nrow = px_dim[1], ncol = px_dim[2], byrow = TRUE)
    rows <- which(rowSums(ink) > 0)
    cols <- which(colSums(ink) > 0)
    if (!length(rows)) return(list(edges = c(t = h, r = w, b = 0, l = 0), touches = FALSE))
    return(list(edges = c(t = h + room - (min(rows) - 1) / dpi,
                          r = max(cols) / dpi - room,
                          b = h + room - max(rows) / dpi,
                          l = (min(cols) - 1) / dpi - room),
                touches = min(rows) == 1 || max(rows) == nrow(ink) || min(cols) == 1 || max(cols) == ncol(ink)))
  }
  for (i in 1:6) {
    # 1. The plot with the current margins, no background (it would count as ink)
    g <- ggplot2::ggplotGrob(set_margins(margins) + ggplot2::theme(plot.background = ggplot2::element_blank()))
    w <- if (is.null(width)) added_up(g)[["w"]] else width
    h <- if (is.null(height)) added_up(g)[["h"]] else height
    # 2. A rough look to see how far things reach, then a fine one
    room <- 8
    repeat {
      rough <- ink_edges(g, w, h, room, dpi = 200)
      if (!rough$touches) break
      if (room >= 64) stop("something reaches more than 64 in past the figure's edge")
      room <- room * 2
    }
    reach <- max(0, rough$edges[["t"]] - h, rough$edges[["r"]] - w, -rough$edges[["b"]], -rough$edges[["l"]])
    edges <- ink_edges(g, w, h, room = reach + 0.25, dpi = res)$edges
    # 3. How far the ink reaches past each edge; pdf() cuts the page to whole points at the top and right
    page_top <- if (is.null(height)) h else floor(h * 72 + 1e-6) / 72
    page_right <- if (is.null(width)) w else floor(w * 72 + 1e-6) / 72
    past <- c(t = edges[["t"]] - page_top, r = edges[["r"]] - page_right, b = -edges[["b"]], l = -edges[["l"]])
    # 4. Just enough margin for the ink to fit, plus pad_pt
    need <- margins + past
    new <- ifelse(need > 0, need + pad_pt / 72, 0)
    new[!names(new) %in% sides] <- 0
    settled <- max(abs(new - margins)) < 0.05 / 72
    margins <- new
    if (settled) break
  }
  # 5. A size added up from the plot, rounded up to whole points
  raw <- added_up(ggplot2::ggplotGrob(set_margins(margins)))
  size_pt <- ceiling(raw * 72 - 1e-6)
  if (is.null(width)) margins[["r"]] <- margins[["r"]] + size_pt[["w"]] / 72 - raw[["w"]]
  if (is.null(height)) margins[["t"]] <- margins[["t"]] + size_pt[["h"]] / 72 - raw[["h"]]
  fitted <- set_margins(margins)
  # 6. Whole points plus a hair, since pdf() truncates the page size
  size <- c(w = if (is.null(width)) (size_pt[["w"]] + 0.001) / 72 else width,
            h = if (is.null(height)) (size_pt[["h"]] + 0.001) / 72 else height)
  return(list(plot = fitted, width = size[["w"]], height = size[["h"]], margins_in = margins))
}

# Save one figure as PDF, PNG (600 dpi) and SVG under one name, cropped to its ink; panel sizes
# are fixed, so the figure's size is added up from them
save_figure <- function(plot, stem, panel_w_mm, panel_h_mm) {
  sized <- plot + theme(panel.widths = unit(panel_w_mm, "mm"), panel.heights = unit(panel_h_mm, "mm"))
  fit <- fit_margins(sized, pad_pt = 0)
  path <- file.path(out_dir, stem)
  ggsave(paste0(path, ".pdf"), fit$plot, width = fit$width, height = fit$height, bg = "transparent")
  ggsave(paste0(path, ".png"), fit$plot, width = fit$width, height = fit$height, dpi = 600, bg = "transparent")
  ggsave(paste0(path, ".svg"), fit$plot, width = fit$width, height = fit$height, bg = "transparent")
  cat(sprintf("%s: %.0f x %.0f pt\n", stem, fit$width * 72, fit$height * 72))
}

# Panel a: growth curves ----------------------------------------------------------------------

# 1. Optical density of three strains every 2 h, from logistic growth with a little noise
set.seed(1)
growth.table <- CJ(STRAIN = c("Wild type", "mutA", "mutB"), HOURS = seq(0, 24, by = 2))
growth.table[, RATE := c("Wild type" = 0.55, "mutA" = 0.42, "mutB" = 0.30)[STRAIN]]
growth.table[, CAPACITY := c("Wild type" = 1.6, "mutA" = 1.4, "mutB" = 1.1)[STRAIN]]
growth.table[, OD600 := CAPACITY / (1 + (CAPACITY / 0.05 - 1) * exp(-RATE * HOURS)) * exp(rnorm(.N, 0, 0.04))]
growth.table[, STRAIN := factor(STRAIN, levels = c("Wild type", "mutA", "mutB"))]

# 2. Lines through the points, one colour per strain
growth.plot <- growth.table %>%
  ggplot(aes(x = HOURS, y = OD600, colour = STRAIN)) +
  geom_line(linewidth = 0.4) +
  geom_point(size = 0.8) +
  scale_colour_manual(values = okabe_ito[c(4, 1, 3)], name = NULL) +
  scale_x_continuous(breaks = seq(0, 24, by = 6), expand = expansion(0)) +
  scale_y_continuous(expand = expansion(0), limits = c(0, 1.8)) +
  labs(x = "Time (h)", y = expression(OD[600])) +
  theme_figure() +
  theme(legend.position = "inside", legend.position.inside = c(0.02, 0.98), legend.justification = c(0, 1))
save_figure(growth.plot, "growth_curves", panel_w_mm = 60, panel_h_mm = 38)

# Panel b: expression bars --------------------------------------------------------------------

# 1. Relative expression of four genes, control and treated, three replicates each
set.seed(2)
expression.table <- CJ(GENE = paste0("gene", 1:4), CONDITION = c("Control", "Treated"), REP = 1:3)
expression.table[, MEAN := fifelse(CONDITION == "Control", 1, c(gene1 = 3.2, gene2 = 1.8, gene3 = 0.6, gene4 = 2.4)[GENE])]
expression.table[, VALUE := MEAN * exp(rnorm(.N, 0, 0.12))]
expression_summary.table <- expression.table[, .(MEAN = mean(VALUE), SD = sd(VALUE)), by = .(GENE, CONDITION)]

# 2. Bars side by side with standard deviations, replicates as points
expression.plot <- expression_summary.table %>%
  ggplot(aes(x = GENE, y = MEAN, fill = CONDITION)) +
  geom_col(position = position_dodge(width = 0.8), width = 0.7) +
  geom_errorbar(aes(ymin = MEAN - SD, ymax = MEAN + SD), position = position_dodge(width = 0.8), width = 0.25,
                linewidth = 0.3, lineend = "round") +
  geom_point(data = expression.table, aes(y = VALUE), position = position_jitterdodge(jitter.width = 0.15, dodge.width = 0.8, seed = 3),
             size = 0.4, colour = "grey20", show.legend = FALSE) +
  scale_fill_manual(values = c(Control = "grey70", Treated = okabe_ito[5]), name = NULL) +
  scale_y_continuous(expand = expansion(0), limits = c(0, 4.2)) +
  labs(x = NULL, y = "Relative expression") +
  theme_figure() +
  theme(legend.position = "inside", legend.position.inside = c(0.98, 0.98), legend.justification = c(1, 1))
save_figure(expression.plot, "expression_bars", panel_w_mm = 60, panel_h_mm = 38)

# Panel c: dose response ----------------------------------------------------------------------

# 1. Response to eight doses of a drug, four replicates, around a Hill curve
set.seed(4)
dose.table <- CJ(DOSE = 10^seq(-2, 2, length.out = 8), REP = 1:4)
dose.table[, RESPONSE := 100 / (1 + (DOSE / 1.5)^1.2) + rnorm(.N, 0, 4)]
curve.table <- data.table(DOSE = 10^seq(-2, 2, length.out = 200))
curve.table[, RESPONSE := 100 / (1 + (DOSE / 1.5)^1.2)]

# 2. The fitted curve over the replicates, dose on a log scale
dose.plot <- dose.table %>%
  ggplot(aes(x = DOSE, y = RESPONSE)) +
  geom_line(data = curve.table, colour = okabe_ito[4], linewidth = 0.5) +
  geom_point(size = 0.8, colour = "grey20") +
  scale_x_log10(breaks = 10^(-2:2), labels = c("0.01", "0.1", "1", "10", "100")) +
  scale_y_continuous(breaks = seq(0, 100, by = 25), limits = c(-10, 110), expand = expansion(0)) +
  labs(x = expression("Dose (" * mu * "M)"), y = "Viability (%)") +
  theme_figure()
save_figure(dose.plot, "dose_response", panel_w_mm = 150, panel_h_mm = 30)
