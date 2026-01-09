//  Dark mode toggle logic
const themeButton = document.getElementById("theme-toggle");

themeButton.addEventListener("click", () => {
    const root = document.documentElement;
    const isDark = root.classList.toggle("dark");
    localStorage.setItem("theme", isDark ? "dark" : "light");
});
