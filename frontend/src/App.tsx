import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Home } from './pages/Home'
import { TaskDetail } from './pages/TaskDetail'
import { Layout } from './components/Layout'

function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/task/:threadId" element={<TaskDetail />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  )
}

export default App
