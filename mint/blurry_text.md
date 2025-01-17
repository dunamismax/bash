Blurry text on Wayland can stem from multiple sources beyond just setting environment variables. Here are several strategies to diagnose and correct the issue:

1. Verify Your Display Settings and Scaling
	•	Native Resolution: Ensure your display resolution is set to the monitor’s native resolution under Settings > Displays.
	•	Scaling Factor: Fractional or non-integer scaling can cause blurry text. Try setting the scaling factor to 100% (no scaling) to see if that improves clarity. If you need scaling for high-DPI displays, try integer values (e.g., 2x) first before using fractional scaling.

2. Adjust Font DPI and Rendering Settings
	•	Font DPI: GNOME allows adjusting the font scaling factor. Open Settings > Universal Access or use the GNOME Tweaks tool (install via sudo apt install gnome-tweaks if needed) to adjust the font scaling factor.
	•	In GNOME Tweaks, under the “Fonts” section, try setting a higher “Scaling Factor” or adjust the “Text Scaling Factor” under Accessibility.
	•	DPI Configurations: Create or edit ~/.config/fontconfig/fonts.conf to set DPI and hinting options. For example:

<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig>
  <match target="font">
    <edit name="dpi" mode="assign"><double>96</double></edit>
  </match>
  <match target="font">
    <edit name="rgba" mode="assign"><const>rgb</const></edit>
  </match>
  <match target="font">
    <edit name="hinting" mode="assign"><bool>true</bool></edit>
  </match>
  <match target="font">
    <edit name="hintstyle" mode="assign"><const>hintslight</const></edit>
  </match>
  <match target="font">
    <edit name="antialias" mode="assign"><bool>true</bool></edit>
  </match>
</fontconfig>

Adjust the dpi value as needed for your display.

3. Check Backend-Specific Options

Since you’re forcing Wayland backends, ensure that:
	•	All applications truly support Wayland rendering. Some apps might still fall back to XWayland, which could behave differently regarding text rendering.
	•	Some Qt or GTK applications may require additional settings for crisp rendering. For instance, setting GDK_DPI_SCALE for GTK apps or similar QT settings might help:

export GDK_DPI_SCALE=1.0
export QT_FONT_DPI=96  # Adjust as necessary

Add these to your environment setup if needed.

4. Clear Cache and Reapply Settings
	•	Font Cache: Clear the font cache to ensure new settings take effect:

fc-cache -f -v


	•	Restart Session: Fully log out and back in (or reboot) after making changes to environment variables or configuration files to ensure they apply system-wide.

5. Fractional Scaling Considerations

If you require fractional scaling:
	•	GNOME’s fractional scaling under Wayland may produce less sharp text. In some cases, enabling experimental fractional scaling may trade off clarity.
	•	Test with different scaling factors to find a balance between size and clarity.
	•	Use gsettings set org.gnome.mutter experimental-features "['scale-monitor-framebuffer']" to enable fractional scaling features if not already enabled.

6. Update System and Drivers
	•	Ensure your graphics drivers and system packages are up to date, as bugs in rendering engines or drivers can affect text clarity.

7. Monitor/Hardware Specifics
	•	Some monitors or cables (e.g., using certain adapters) might cause a soft display. Verify the cable and monitor configuration.

By systematically adjusting these settings, you can usually resolve blurry text issues on Ubuntu under Wayland. If problems persist, consider looking up bug reports or forums specific to your GPU, display hardware, or application to see if others have found a resolution.