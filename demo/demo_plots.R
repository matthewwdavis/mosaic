# mosaic demo plots
# Four small figures from R's built-in data (iris, ToothGrowth, PlantGrowth, ChickWeight), each saved as PDF, PNG and
# SVG in ./Figures/demo/. Change a setting below, run the script again, then press Refresh All Pictures (⌘⇧R) in
# mosaic: the placed figures update where they are.
# Run from this folder: Rscript demo_plots.R (in RStudio, setwd() to this folder and source the script)

# Libraries ------------------------------------------------------------------------------------------------------------
library(ggplot2)
library(data.table)
library(magrittr)
source("./demo_helpers.R")   # fit_margins() and save_figure()

# Settings: change these -----------------------------------------------------------------------------------------------

# Colours (hex codes), one per group, named as the group appears in the legend or on the axis
species.colours <- c("setosa" = "#E69F00", "versicolor" = "#56B4E9", "virginica" = "#009E73")
supplement.colours <- c("Orange juice" = "#E69F00", "Vitamin C" = "#0072B2")
plant.colours <- c("Control" = "#999999", "Treatment 1" = "#56B4E9", "Treatment 2" = "#D55E00")
diet.colours <- c("Diet 1" = "black", "Diet 2" = "#56B4E9", "Diet 3" = "#009E73", "Diet 4" = "#CC79A7")
ink.colour <- "#000000"   # text, axes, ticks and error bars

# Text sizes (pt): titles, and the small text (tick and legend labels). Journals ask for at least 5 pt (set the small
# text to 4 to see mosaic's Check flag it); pdf() rounds text to whole points
title_text.pt <- 6
small_text.pt <- 5

# Points and lines (pt)
point.pt <- 1.5        # point diameter
axis_line.pt <- 0.25   # axes, ticks, error bars and box outlines
data_line.pt <- 0.5    # the time course's lines

# Figure sizes (mm): each saved figure's width and height, rounded up to whole points
scatter_size.mm <- c(width = 60, height = 45)
bars_size.mm <- c(width = 60, height = 45)
box_size.mm <- c(width = 45, height = 45)
time_course_size.mm <- c(width = 60, height = 45)

# Theme ----------------------------------------------------------------------------------------------------------------

# ggplot's linewidth for a line that many pt wide (R draws line widths in 1/96 in, not 1/72)
linewidth_for <- function(pt) {
  return(pt * 96 / 72 / .pt)
}

# ggplot's point size for a point.pt-wide dot: a solid point (shape 16, no outline) is 0.75 x its font size across
point_size <- point.pt / (0.75 * .pt)

# Shared look: theme_classic in Helvetica with the sizes and ink colour above, 0.2 cm legend keys, no margins
# (save_figure() fits them to the ink) and transparent backgrounds
demo.theme <- theme_classic(base_size = title_text.pt, base_family = "Helvetica", base_line_size = linewidth_for(axis_line.pt),
                            base_rect_size = linewidth_for(axis_line.pt), ink = ink.colour) +
  theme(axis.text = element_text(size = small_text.pt),
        legend.text = element_text(size = small_text.pt),
        strip.text = element_text(size = small_text.pt),
        plot.caption = element_text(size = small_text.pt),
        legend.key.size = unit(0.2, "cm"),
        legend.margin = margin(0, 0, 0, 0),
        legend.box.spacing = unit(2, "pt"),
        plot.margin = margin(0, 0, 0, 0),
        plot.background = element_rect(fill = NA, colour = NA),
        panel.background = element_rect(fill = NA, colour = NA),
        legend.background = element_blank(),
        legend.box.background = element_blank())

# 1. Scatter: petal length against width, by species ------------------------------------------------------------------

# Iris measurements, one row per flower
iris.table <- as.data.table(iris)
setnames(iris.table, c("SEPAL_LENGTH", "SEPAL_WIDTH", "PETAL_LENGTH", "PETAL_WIDTH", "SPECIES"))

# Plot: axes from 0, points at the panel's edge drawn whole (clip off)
scatter.plot <- iris.table %>%
  ggplot(aes(x = PETAL_LENGTH, y = PETAL_WIDTH, colour = SPECIES)) +
  geom_point(shape = 16, size = point_size, stroke = 0) +
  scale_colour_manual(values = species.colours) +
  scale_x_continuous(limits = c(0, 7), breaks = 0:7, expand = expansion(0)) +
  scale_y_continuous(limits = c(0, 2.5), breaks = seq(0, 2.5, 0.5), expand = expansion(0)) +
  coord_cartesian(clip = "off") +
  labs(x = "Petal length (cm)", y = "Petal width (cm)", colour = "Species") +
  demo.theme

# Save
save_figure(scatter.plot, "./Figures/demo/iris_petal_scatter", scatter_size.mm)

# 2. Bars: mean tooth length ± SE, by dose and supplement --------------------------------------------------------------

# Mean and standard error for each supplement and dose
tooth_summary.table <- as.data.table(ToothGrowth)[, .(MEAN = mean(len), SE = sd(len) / sqrt(.N)), by = .(SUPP = supp, DOSE = dose)]
tooth_summary.table[, SUPPLEMENT := fifelse(SUPP == "OJ", "Orange juice", "Vitamin C")]
tooth_summary.table[, DOSE := factor(DOSE)]

# Plot: bars side by side for each dose, error bars over them
bars.plot <- tooth_summary.table %>%
  ggplot(aes(x = DOSE, y = MEAN, fill = SUPPLEMENT)) +
  geom_col(position = position_dodge(width = 0.8), width = 0.7) +
  geom_errorbar(aes(ymin = MEAN - SE, ymax = MEAN + SE), position = position_dodge(width = 0.8), width = 0.3,
                linewidth = linewidth_for(axis_line.pt), colour = ink.colour) +
  scale_fill_manual(values = supplement.colours) +
  scale_y_continuous(limits = c(0, 30), breaks = seq(0, 30, 10), expand = expansion(0)) +
  labs(x = "Vitamin C dose (mg/day)", y = "Tooth length", fill = "Supplement") +
  demo.theme

# Save
save_figure(bars.plot, "./Figures/demo/tooth_length_bars", bars_size.mm)

# 3. Box plot: plant dry weight by treatment, every plant shown --------------------------------------------------------

# Plant weights, one row per plant, groups named as in plant.colours
plant.table <- as.data.table(PlantGrowth)
setnames(plant.table, c("WEIGHT", "GROUP"))
plant.table[, GROUP := factor(GROUP, levels = c("ctrl", "trt1", "trt2"), labels = c("Control", "Treatment 1", "Treatment 2"))]

# Plot: boxes without their outlier points (every plant is drawn over them), jittered the same way each run
box.plot <- plant.table %>%
  ggplot(aes(x = GROUP, y = WEIGHT, colour = GROUP)) +
  geom_boxplot(width = 0.6, fill = NA, linewidth = linewidth_for(axis_line.pt), outlier.shape = NA) +
  geom_point(position = position_jitter(width = 0.15, height = 0, seed = 1), shape = 16, size = point_size, stroke = 0) +
  scale_colour_manual(values = plant.colours) +
  scale_y_continuous(limits = c(3, 7), breaks = 3:7, expand = expansion(0)) +
  labs(x = NULL, y = "Dry weight (g)") +
  demo.theme +
  theme(legend.position = "none")

# Save
save_figure(box.plot, "./Figures/demo/plant_weight_box", box_size.mm)

# 4. Time course: mean chick weight by day, one line per diet ----------------------------------------------------------

# Mean weight for each diet on each day weighed
chick_summary.table <- as.data.table(ChickWeight)[, .(MEAN = mean(weight)), by = .(DAY = Time, DIET = paste("Diet", Diet))]

# Plot: lines with a point on each day weighed; points on the axes drawn whole (clip off)
time_course.plot <- chick_summary.table %>%
  ggplot(aes(x = DAY, y = MEAN, colour = DIET)) +
  geom_line(linewidth = linewidth_for(data_line.pt)) +
  geom_point(shape = 16, size = point_size, stroke = 0) +
  scale_colour_manual(values = diet.colours) +
  scale_x_continuous(limits = c(0, 21), breaks = seq(0, 21, 7), expand = expansion(0)) +
  scale_y_continuous(limits = c(0, 300), breaks = seq(0, 300, 100), expand = expansion(0)) +
  coord_cartesian(clip = "off") +
  labs(x = "Day", y = "Weight (g)", colour = NULL) +
  demo.theme

# Save
save_figure(time_course.plot, "./Figures/demo/chick_weight_time_course", time_course_size.mm)
