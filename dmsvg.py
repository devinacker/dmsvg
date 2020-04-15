#!/usr/bin/env python3
"""
	dmsvg - Doom map SVG renderer
	by Revenant
	
	Scroll down for render settings.
	
	Copyright (c) 2020 Devin Acker

	Permission is hereby granted, free of charge, to any person obtaining a copy
	of this software and associated documentation files (the "Software"), to deal
	in the Software without restriction, including without limitation the rights
	to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
	copies of the Software, and to permit persons to whom the Software is
	furnished to do so, subject to the following conditions:

	The above copyright notice and this permission notice shall be included in
	all copies or substantial portions of the Software.

	THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
	IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
	FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
	AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
	LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
	OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
	THE SOFTWARE.

"""

from omg import *
from sys import argv, stderr, exit
from PIL import Image
from xml.etree import ElementTree
from io import BytesIO
from base64 import b64encode
from argparse import ArgumentParser
from math import atan2, pi, inf

class MapShape():
	# store a shape and its approximate size, so we can draw largest ones first
	# and also eliminate duplicate shapes in case we end up tracing something twice
	def __init__(self, lines, sector):
		self.lines = lines
		self.sector = sector
		
		box_top    = min([line.point_top   for line in lines])
		box_left   = min([line.point_left  for line in lines])
		box_bottom = max([line.point_right for line in lines])
		box_right  = max([line.point_right for line in lines])
		self.box = (box_top, box_left, box_bottom, box_right)
		self.box_area = (box_bottom - box_top) * (box_right - box_left)

	def __eq__(self, other):
		return self.box == other.box and self.lines == other.lines

	def __lt__(self, other):
		return self.box_area < other.box_area

class DrawMap():
	#
	# default parameters (these can be changed from the command line)
	#
	# size of border in map units
	border = 8
	# background (None = transparent)
	fill   = None
	stroke = None
	
	def __init__(self, wad, mapname):
		self.edit = MapEditor(wad.maps[mapname])
		
		self.xmin = min([ v.x for v in self.edit.vertexes])
		self.xmax = max([ v.x for v in self.edit.vertexes])
		self.ymin = min([-v.y for v in self.edit.vertexes])
		self.ymax = max([-v.y for v in self.edit.vertexes])
		
		width  = self.xmax - self.xmin + 2*self.border
		height = self.ymax - self.ymin + 2*self.border
		
		# normalize Y axis
		for v in self.edit.vertexes:
			v.y = -v.y
		
		# stash some useful line info for later
		for num, line in enumerate(self.edit.linedefs):
			line.id = num
			line.sector_front = self.edit.sidedefs[line.front].sector
			if line.two_sided:
				line.sector_back = self.edit.sidedefs[line.back].sector
			else:
				line.sector_back = -1
			
			vx_a = self.edit.vertexes[line.vx_a]
			vx_b = self.edit.vertexes[line.vx_b]
			
			line.point_top    = min(vx_a.y, vx_b.y)
			line.point_bottom = max(vx_a.y, vx_b.y)
			line.point_left   = min(vx_a.x, vx_b.x)
			line.point_right  = max(vx_a.x, vx_b.x)
			
			dy = vx_b.y - vx_a.y
			dx = vx_b.x - vx_a.x
			line.angle = atan2(dx, dy) % (2 * pi)
			if dx != 0:
				line.slope = abs(dy) / abs(dx)
			else:
				line.slope = inf
			
		#	print("line %d angle is %d" % (num, line.angle * 180 / pi))
		
		# group lines by sector and vertex for faster searching later
		self.lines_at_vertex = [{} for s in self.edit.sectors]
		self.lines_in_sector = [[] for s in self.edit.sectors]
		def addline_sv(sector, vertex, line):
			if vertex not in self.lines_at_vertex[sector]:
				self.lines_at_vertex[sector][vertex] = []
			self.lines_at_vertex[sector][vertex].append(line)
		
		def addline_s(sector, line):
			addline_sv(sector, line.vx_a, line)
			addline_sv(sector, line.vx_b, line)
			self.lines_in_sector[sector].append(line)
		
		def addline(line):
			if line.two_sided:
				if line.sector_front != line.sector_back:
					# ignore 2s lines w/ same sector on both sides
					addline_s(line.sector_front, line)
					addline_s(line.sector_back, line)
			else:
				addline_s(line.sector_front, line)
		
		for line in self.edit.linedefs:
			addline(line)
		
		# initialize image
		self.svg = ElementTree.Element('svg')
		self.svg.attrib['xmlns'] = "http://www.w3.org/2000/svg"
		self.svg.attrib['viewBox'] = "%d %d %u %u" % (self.xmin - self.border, self.ymin - self.border, width, height)
		if self.stroke:
			self.svg.attrib['stroke'] = self.stroke
		if self.fill:
			self.svg.attrib['fill'] = self.fill

		# define patterns for all flats in map
		defs = ElementTree.SubElement(self.svg, 'defs')
		floors = set([s.tx_floor for s in self.edit.sectors])
		for f in floors:
			try:
				img = wad.flats[f].to_Image()
				img_data = BytesIO()
				img.save(img_data, "png")
			except KeyError:
				continue
		
			pattern = ElementTree.SubElement(defs, 'pattern')
			pattern.attrib['id'] = f
			pattern.attrib['patternUnits'] = "userSpaceOnUse"
			pattern.attrib['width'] = str(img.width)
			pattern.attrib['height'] = str(img.height)
			
			image = ElementTree.SubElement(pattern, 'image')
			image.attrib['href'] = "data:image/png;base64," + str(b64encode(img_data.getvalue()), 'ascii')
			image.attrib['x'] = "0"
			image.attrib['y'] = "0"
			image.attrib['width'] = str(img.width)
			image.attrib['height'] = str(img.height)

		# brightness filters
		lights = set([s.light >> 3 for s in self.edit.sectors])
		for light in lights:
			filter = ElementTree.SubElement(defs, 'filter')
			filter.attrib['id'] = "light" + str(light)
			transfer = ElementTree.SubElement(filter, 'feComponentTransfer')
			funcR = ElementTree.SubElement(transfer, 'feFuncR')
			funcG = ElementTree.SubElement(transfer, 'feFuncG')
			funcB = ElementTree.SubElement(transfer, 'feFuncB')
			funcR.attrib['type'] = "linear"
			# a lighting curve that i basically pulled out of my ass
			funcR.attrib['slope'] = str(1.5 * (light/32)**2)
			funcG.attrib = funcR.attrib
			funcB.attrib = funcR.attrib

		# add opaque background if specified
		if self.fill:
			bg = ElementTree.SubElement(self.svg, 'rect')
			bg.attrib['stroke'] = self.fill # color the border too
			bg.attrib['x'] = str(self.xmin - self.border)
			bg.attrib['y'] = str(self.ymin - self.border)
			bg.attrib['width'] = str(width)
			bg.attrib['height'] = str(height)

	def draw_lines(self, shape):
		if len(shape.lines) < 2:
			return
	
		flat = None
		light = None
		if shape.sector >= 0:
			try:
				flat = self.edit.sectors[shape.sector].tx_floor
				light = self.edit.sectors[shape.sector].light >> 3
			except IndexError:
				pass
		
		if shape.lines[0].vx_a in (shape.lines[1].vx_a, shape.lines[1].vx_b):
			last_vx = self.edit.vertexes[shape.lines[0].vx_b]
		else:
			last_vx = self.edit.vertexes[shape.lines[0].vx_a]
		
		d = "M %d,%d " % (last_vx.x, last_vx.y)
		
		for line in shape.lines:
			vx_a = self.edit.vertexes[line.vx_a]
			vx_b = self.edit.vertexes[line.vx_b]
			if last_vx == vx_a:
				d += "L %d,%d " % (vx_b.x, vx_b.y)
				last_vx = vx_b
			else:
				d += "L %d,%d " % (vx_a.x, vx_a.y)
				last_vx = vx_a
		d += "z"
		
		path = ElementTree.SubElement(self.svg, 'path')
		path.attrib['d'] = d
		if flat:
			path.attrib['fill'] = "url(#%s)" % flat
			if light:
				path.attrib['filter'] = "url(#light%d)" % light
		elif not self.fill:
			path.attrib['fill'] = "rgba(0,0,0,0)"
	
	def linesort(self, line):
		# sort by the following, in order:
		# left-most vertex
		# top-most vertex
		# slope
		return (line.point_left, line.point_top, line.slope)
	
	def trace_lines(self, line):
		visited = []
		
		# first, which sector are we looking at?
		two_sided = line.two_sided
		use_front = False
		if line.angle > 0 and line.angle <= pi:
			use_front = True
		
		sector = line.sector_front
		if line.two_sided and not use_front:
			sector = line.sector_back
	#	print("visiting sector %u from line %u, use_front = %s" % (sector, line.id, use_front))
		
		last_vx = line.vx_b
		
		while True:
			visited.append(line)
			
			# find another line with other connected point, same sector
			next_lines = self.lines_at_vertex[sector][last_vx]
			next_lines = [other for other in next_lines if other not in visited]
			
			if len(next_lines) == 0:
				break
			
			line = next_lines[0]
			last_vx = line.vx_a if last_vx == line.vx_b else line.vx_b
		
		if not two_sided and not use_front:
			# we used the front of this 1s line for finding adjacent lines,
			# but don't use it for rendering empty space
			sector = -1
		
		return MapShape(visited, sector)
	
	def save(self, filename):
		shapes = []
		
		for lines_left in self.lines_in_sector:
			lines_left.sort(key = self.linesort)
			while len(lines_left) > 0:
				try:
					shape = self.trace_lines(lines_left[0])
					if shape not in shapes:
						shapes.append(shape)
					for line in shape.lines:
						if line in lines_left:
							lines_left.remove(line)
							
				except KeyboardInterrupt:
					print("\nRendering canceled.")
					exit(-1)
		
		# draw shapes largest to smallest
		shapes.sort(reverse = True)
		for shape in shapes:
			self.draw_lines(shape)
		
		ElementTree.ElementTree(self.svg).write(filename)
		print("Rendered %s." % filename)

def get_args():
	ap = ArgumentParser()
	ap.add_argument("filenames", help="path to WAD file(s)", nargs='*')
	ap.add_argument("map",      help="name of map (ex. MAP01, E1M1)")
	
	ap.add_argument("-o", "--output",
	                help="output file name (default: based on WAD name)")
	ap.add_argument("-b", "--border", type=int, default=DrawMap.border,
	                help="size of border (default: %(default)s)")
	ap.add_argument("-s", "--stroke", default=DrawMap.stroke,
	                help="stroke color/pattern (ex. white, #FFFFFF) (default: none)")
	ap.add_argument("-f", "--fill", default=DrawMap.fill,
	                help="default fill color/pattern (ex. black, #000000) (default: none)")

	if len(argv) < 3:
		ap.print_help()
		exit(-1)
	
	return ap.parse_args()
	
if __name__ == "__main__":
	print("dmsvg - Doom map SVG renderer")
	print("by Devin Acker (Revenant), 2020\n")
	
	args = get_args()
	
	filenames = args.filenames
	mapname   = args.map.upper()
	output    = args.output or "%s_%s.svg" % (filenames[-1], mapname)
	
	# apply optional arguments to DrawMap settings
	DrawMap.border = args.border
	DrawMap.stroke = args.stroke
	DrawMap.fill   = args.fill
	
	# load specified WAD(s)
	wad = WAD()
	for filename in filenames:
		try:
			wad.from_file(filename)	
		except AssertionError:
			stderr.write("Error: Unable to load %s.\n" % filename)
			exit(-1)
	
	if mapname not in wad.maps:
		stderr.write("Error: Map %s not found in WAD.\n" % mapname)
		exit(-1)
	
	try:
		draw = DrawMap(wad, mapname)
		draw.save(output)
	except ValueError as e:
		stderr.write("Error: %s.\n" % e)
		exit(-1)
	