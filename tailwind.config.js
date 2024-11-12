module.exports = {
  content: ["./templates/**/*.html"],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#9333EA',
          dark: '#7928D1',
          light: '#A855F7'
        },
        background: {
          DEFAULT: '#0A051A',
          light: '#1a1128',
          dark: '#050210'
        },
        surface: {
          DEFAULT: '#1E1435',
          light: '#2d1f4f',
          dark: '#150d28'
        }
      },
      fontFamily: {
        sans: ['Familjen Grotesk', 'sans-serif']
      },
      animation: {
        'float': 'float 3s ease-in-out infinite',
        'shimmer': 'shimmer 2s infinite linear',
        'fade': 'fade 0.3s ease-in-out'
      },
      keyframes: {
        float: {
          '0%, 100%': { transform: 'translateY(0px) rotate(0deg)' },
          '50%': { transform: 'translateY(-10px) rotate(5deg)' }
        },
        shimmer: {
          '0%': { transform: 'translateX(-100%)' },
          '100%': { transform: 'translateX(100%)' }
        },
        fade: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' }
        }
      }
    }
  },
  plugins: []
}
