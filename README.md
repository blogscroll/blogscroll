# 📜 BlogScroll

![Blog deployment](https://github.com/blogscroll/blogscroll/workflows/Blog%20deployment/badge.svg)

An open directory of personal sites and blogs, maintained entirely on GitHub.

## 🏗 What is this?

This project was created by [Den Delimarsky](https://den.dev/) in an effort to bring attention to little [digital gardens](https://maggieappleton.com/garden-history) and personal corners of the internet that people maintain outside, well - walled gardens.

A few years back, I found that I really enjoy reading people's personal stories and discovering their work outside social networks. However, as it turns out there is no one place that I can visit to see what people are building, so I decided to whip this page up myself.

![A screenshot of the BlogScroll project](screenshot.png)

And it goes without saying that this site is work in progress - your feedback is [very much welcome](https://github.com/blogscroll/blogscroll/issues)!

## ❓ FAQ

### How did you come up with the initial list of sites?

I actually just moved my bookmarks to the web. That's it - that's the complicated logic I used to compile the initial list. But the site took a life of its own with community contributions.

### Can I add any site?

**Not quite**. I am very intentional about this project being a directory of sites that people manage **within their own domains**. The goal is to create an environment for serendipitous discovery of digital gardens and personal pages that are outside the typical social media/newsletter aggregation sites.

Here is a simple (**yet not comprehensive)** breakdown of what may be approved and what may not:

#### ✅ OK to submit

- Sites hosted on common blogging services **with a custom domain attached**.
- Personal sites hosted on open-source services, like GitHub Pages (e.g., a page like `https://dend.github.io` is OK).
- Personal portfolios.
- Personal wiki sites.
- Self-hosted blogs.

#### 🛑 Not OK to submit

- Sites hosted on Blogger, LiveJournal, Substack, Medium, or any other service **without a custom domain attached**.
- Twitter, Facebook, LinkedIn, or other social media links.
- Links to companies or websites representing personal companies, whose primary purpose is to sell or promote a product.
- Sites that contain Not Safe For Work (NSFW) material (e.g., nudity, gore, disturbing imagery). While we're all adults here, the directory is designed to be fit for consumption anywhere (home, workplace, school, public transit). It would be a very unpleasant surprise to randomly stumble across content that may be classified as inappropriate just by clicking a blog link.
- Sites that contain or allude to hate speech, abuse, or otherwise harmful material.
- Sites that have a primary purpose other than being a personal page (e.g., podcasts, streaming pages, project pages).

>[!WARNING]
>Any sites that are found to be in violation of these guidelines _even after submission_ will be removed with no notice, and there's a good chance that you won't be able to submit more pages in the future.

Lastly, and I want to spell this out directly - I reserve the right to not include or publish any site on BlogScroll. Because this is _my_ project, I get to choose how I curate it.

### Can I remove my site from the list?

**Absolutely**. [Open an issue](https://github.com/blogscroll/blogscroll/issues/new?assignees=dend&labels=bug%2Cneeds-triage&projects=&template=4-report-url.yml&title=%5BURL+Report%5D%3A+) or [create a pull request](https://github.com/blogscroll/blogscroll/pulls).

>[!NOTE]
>This can only be done for sites you own, or if the site has an issue, [outlined below](#can-i-remove-someone-elses-site).

### Can I remove someone else's site?

**Not really**. Short of that site being no longer available, or hosting abusive, harmful, or inappropriate content, you can only remove the site that you manage or previously added.

If the site is problematic for any of the reasons above, [open a site report issue](https://github.com/blogscroll/blogscroll/issues/new?assignees=dend&labels=bug%2Cneeds-triage&projects=&template=4-report-url.yml&title=%5BURL+Report%5D%3A+).

### A site is no longer active/returns a 404. Can it be removed?

**Totally**. [Open an issue](https://github.com/blogscroll/blogscroll/issues/new?assignees=dend&labels=bug%2Cneeds-triage&projects=&template=4-report-url.yml&title=%5BURL+Report%5D%3A+) or [create a pull request](https://github.com/blogscroll/blogscroll/pulls) - I'll help fix the problem. Make sure to mention that the site is no longer available.

### A site seems to be hosting questionable content. What should I do?

You're probably sick of hearing this, but [open an issue](https://github.com/blogscroll/blogscroll/issues/new?assignees=dend&labels=bug%2Cneeds-triage&projects=&template=4-report-url.yml&title=%5BURL+Report%5D%3A+) or [create a pull request](https://github.com/blogscroll/blogscroll/pulls). This will be the fastest way to address it.

### I don't like the categories that are laid out. Can I change them?

The categories are by no means final, so if you have a suggestion on how to make those better, [open an issue](https://github.com/blogscroll/blogscroll/issues) first. **Do not submit a pull request** until you have an issue open, and it was agreed that the category makes sense.

### Can I put my blog into more than one category?

**No**. I am trying to keep the list fairly clean and simple, so your site can only be included in one category.

### Can I link to my social media instead?

**No**. Just personal sites, please.

### Can I include a link to my company/startup/business/consulting/project site?

Same as above - just personal sites, please.

### I want to create a pull request and add my site. What do I do?

Fork the repository, then add a new TOML entry for your site in the [`categories`](https://github.com/blogscroll/blogscroll/tree/main/web/data/categories) folder, in the respective `list.toml` file.

Basically, you need four data points - the URL, name of the person who the site belongs to, a link to the favicon (on the same domain as the site), and the last updated date that maps to the date when you made the change.

The identifier for the site (in square brackets) should be the blog apex domain, including the TLD, with spaces, periods, and dashes removed. So, `https://den.dev` becomes `[blogs.dendev]`.

### Can I submit more than one site?

**You can**. You will need to open several site requests for that.

That being said, sites should still fit the [criteria above](#can-i-add-any-site).

If you have more than one blog, submit the one that represents you best.
